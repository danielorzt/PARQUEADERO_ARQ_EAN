"""Controlador de la simulación: un hilo despachador y un hilo por vehículo.

Todos los métodos públicos no bloquean, salvo join(). Reset incrementa un token de generación
en lugar de esperar a los hilos anteriores; los consumidores descartan los eventos cuya generación difiere
de `Simulation.generation`.
"""
import queue
import random
import threading
import time
from collections import deque
from dataclasses import replace

from parking.clock import SimClock
from parking.events import EventEmitter, EventKind
from parking.lot import ParkingLot
from parking.plans import generate_plans
from parking.policies import FifoPolicy
from parking.vehicle import vehicle_worker

_ADD = object()
_SHUTDOWN_JOIN = 2.0  # segundos reales que el despachador espera a sus vehículos al detener


class RunContext:
    """Todo lo que pertenece a una generación (una ejecución)."""

    def __init__(self, config, generation, out_queue):
        self.config = config
        self.generation = generation
        self.poll = config.poll
        self.emitter = EventEmitter(out_queue, generation)
        self.clock = SimClock(config.time_scale)
        self.stop = threading.Event()
        self.running = threading.Event()
        self.running.set()
        self.finished = threading.Event()
        self.lot = ParkingLot(config.capacity, make_policy(config), self.emitter,
                              self.clock, self.stop, self.running, config.poll)
        self.rng = random.Random(config.seed)
        self.plans = generate_plans(config, self.rng)
        self.next_id = config.num_vehicles + 1
        self.add_queue = queue.Queue()
        self.lock = threading.Lock()  # lock hoja: protege solo los campos de abajo
        self.vehicle_threads = []
        self.dispatcher = None
        self.started = False
        self.stopped = False
        self.closing = False  # ya no se acepta Add cuando el despachador decidió terminar


def make_policy(config):
    if config.policy == "priority":
        from parking.policies import PriorityPolicy  # unidad de extras; no existe en el núcleo MVP
        return PriorityPolicy(config.aging_rate)
    return FifoPolicy()


class Simulation:
    def __init__(self, config, out_queue):
        config.validate()
        self._queue = out_queue
        self._lock = threading.Lock()  # protege solo los cambios de _ctx/_all_ctx; nunca se mantiene mientras se espera
        self._ctx = RunContext(config, 0, out_queue)
        self._all_ctx = [self._ctx]

    @property
    def generation(self):
        return self._ctx.generation

    @property
    def finished(self):
        return self._ctx.finished

    def start(self):
        ctx = self._ctx
        with ctx.lock:
            if ctx.started:
                return
            ctx.started = True
        ctx.clock.restart()
        ctx.emitter.emit(EventKind.STARTED, 0.0)
        ctx.dispatcher = threading.Thread(
            target=_dispatch, args=(ctx,), name="gen%d-dispatcher" % ctx.generation,
            daemon=True)
        ctx.dispatcher.start()

    def add_vehicle(self):
        """Encola un vehículo adicional; devuelve False cuando la ejecución ya no puede aceptarlo."""
        ctx = self._ctx
        with ctx.lock:
            if ctx.closing or ctx.stop.is_set():
                return False
            ctx.add_queue.put(_ADD)
        return True

    def pause(self):
        ctx = self._ctx
        if ctx.running.is_set():
            ctx.running.clear()
            ctx.clock.pause()
            ctx.emitter.emit(EventKind.PAUSED, ctx.clock.now())

    def resume(self):
        ctx = self._ctx
        if not ctx.running.is_set() and not ctx.stop.is_set():
            ctx.clock.resume()
            ctx.running.set()
            ctx.lot.wake()
            ctx.emitter.emit(EventKind.RESUMED, ctx.clock.now())

    def set_speed(self, time_scale):
        ctx = self._ctx
        ctx.clock.set_scale(time_scale)  # valida (ValueError)
        ctx.emitter.emit(EventKind.SPEED, ctx.clock.now())

    def stop(self):
        _stop_ctx(self._ctx)

    def reset(self, config):
        """Detiene la ejecución actual e inicia una nueva en reposo; nunca espera a los hilos anteriores."""
        config.validate()
        with self._lock:
            _stop_ctx(self._ctx)
            ctx = RunContext(config, self._ctx.generation + 1, self._queue)
            self._ctx = ctx
            self._all_ctx.append(ctx)
        ctx.emitter.emit(EventKind.RESET, 0.0)

    def join(self, timeout):
        """Une todos los hilos de todas las generaciones; devuelve True cuando todos han terminado."""
        deadline = time.monotonic() + timeout
        with self._lock:
            contexts = list(self._all_ctx)
        for ctx in contexts:
            with ctx.lock:
                threads = [ctx.dispatcher] + ctx.vehicle_threads
            for thread in threads:
                if thread is not None:
                    thread.join(max(0.0, deadline - time.monotonic()))
        return all(not t.is_alive() for ctx in contexts for t in
                   [ctx.dispatcher] + ctx.vehicle_threads if t is not None)


def _stop_ctx(ctx):
    with ctx.lock:
        if ctx.stopped:
            return
        ctx.stopped = True
        started = ctx.started
    ctx.stop.set()
    ctx.running.set()  # desbloquea lo que esté esperando una pausa
    ctx.add_queue.put(None)  # despierta de inmediato al despachador
    ctx.lot.wake()
    ctx.emitter.emit(EventKind.STOPPED, ctx.clock.now())
    if not started:
        ctx.finished.set()


def _dispatch(ctx):
    """Emite turnos en orden de plan, para que el orden de llegada sea determinista (planificador a largo plazo)."""
    pending = deque(ctx.plans)
    try:
        while not ctx.stop.is_set():
            now = ctx.clock.now()
            if pending and pending[0].arrival_time <= now:
                _issue(ctx, pending.popleft())
                continue
            if not pending and all(not t.is_alive() for t in ctx.vehicle_threads):
                with ctx.lock:
                    if ctx.add_queue.empty():
                        ctx.closing = True
                        break
                # Hay un Add encolado: se pasa al get temporizado de abajo, que lo consume
                # (un `continue` simple aquí haría un bucle ocupado sin vaciarlo nunca).
            wait = ctx.poll
            if pending:
                wait = min(wait, max(0.0, ctx.clock.real_duration(pending[0].arrival_time - now)))
            try:
                item = ctx.add_queue.get(timeout=wait)
            except queue.Empty:
                continue
            if item is _ADD:
                _issue(ctx, _make_added_plan(ctx))
        if not ctx.stop.is_set():
            ctx.emitter.emit(EventKind.FINISHED, ctx.clock.now())
        else:
            deadline = time.monotonic() + _SHUTDOWN_JOIN
            for thread in list(ctx.vehicle_threads):
                thread.join(max(0.0, deadline - time.monotonic()))
    finally:
        ctx.finished.set()


def _make_added_plan(ctx):
    config = replace(ctx.config, num_vehicles=1, arrival_gap=(0.0, 0.0))
    plan = generate_plans(config, ctx.rng, start_id=ctx.next_id, start_time=ctx.clock.now())[0]
    ctx.next_id += 1
    return plan


def _issue(ctx, plan):
    ticket = ctx.lot.issue_ticket(plan)
    thread = threading.Thread(
        target=vehicle_worker, args=(plan, ticket, ctx),
        name="gen%d-vehicle-%d" % (ctx.generation, plan.vehicle_id), daemon=True)
    with ctx.lock:
        ctx.vehicle_threads.append(thread)
    thread.start()
