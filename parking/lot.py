"""El parqueadero: un monitor de admisión construido con cuatro primitivas de sincronización.

Analogía de SO: Semaphore(capacity) = semáforo de conteo sobre el conjunto de espacios (P/V),
count_lock = mutex del contador de ocupación, Condition = monitor / cola de
listos; los Event stop/running son señales.

Orden de bloqueo (orden total; nunca adquirir un número menor mientras se mantiene uno mayor):
    L1 _cond  ->  L2 _count_lock  ->  L3 emitter lock (leaf)
El Semaphore solo se adquiere sin bloqueo, así que nunca se espera sobre él mientras se
mantiene un Lock (sin retener y esperar), y toda espera bloqueante tiene tiempo límite.
"""
import threading

from parking.events import EventKind


class ParkingLot:
    def __init__(self, capacity, policy, emitter, clock, stop, running, poll):
        self._capacity = capacity
        self._policy = policy
        self._emitter = emitter
        self._clock = clock
        self._stop = stop
        self._running = running
        self._poll = poll
        self._sem = threading.Semaphore(capacity)
        self._cond = threading.Condition()  # L1
        self._count_lock = threading.Lock()  # L2
        self._next_ticket = 0  # protegido por L1
        self._plans = {}  # turno -> plan, protegido por L1
        self._waiting = 0  # == len(policy); se escribe bajo L1 y en otros lugares se lee como entero simple
        self._occupied = 0  # protegido por L2
        self._free = set(range(1, capacity + 1))  # números de espacios libres, protegidos por L2

    @property
    def capacity(self):
        return self._capacity

    def issue_ticket(self, plan):
        """Encola un vehículo que llega (hilo despachador) y devuelve su turno."""
        with self._cond:
            ticket = self._next_ticket
            self._next_ticket += 1
            self._plans[ticket] = plan
            now = self._clock.now()
            self._policy.push(ticket, plan.vehicle_id, plan.priority, now)
            self._waiting = len(self._policy)
            self._emit(EventKind.ARRIVED, now, plan, ticket, priority=plan.priority)
            self._cond.notify_all()
            return ticket

    def await_admission(self, ticket):
        """Bloquea hasta ser admitido; devuelve el número de espacio, o None cuando se detiene."""
        with self._cond:
            plan = self._plans[ticket]
            while True:
                now = self._clock.now()
                if self._stop.is_set():
                    self._dequeue(ticket)
                    self._emit(EventKind.CANCELLED, now, plan, ticket)
                    del self._plans[ticket]
                    self._cond.notify_all()
                    return None
                if (self._running.is_set() and self._policy.head(now) == ticket
                        and self._sem.acquire(blocking=False)):
                    self._dequeue(ticket)
                    with self._count_lock:  # L2 mientras se mantiene L1: orden permitido
                        self._occupied += 1
                        slot = min(self._free)
                        self._free.discard(slot)
                        self._emit(EventKind.PARKED, now, plan, ticket, slot=slot,
                                   occupied=self._occupied)
                    self._cond.notify_all()  # la nueva cabeza vuelve a verificar
                    return slot
                self._cond.wait(timeout=self._poll)

    def leave(self, ticket, slot):
        """Libera un espacio. Llamar solo si await_admission devolvió ese espacio."""
        with self._cond:
            plan = self._plans.pop(ticket)
        with self._count_lock:  # L1 ya liberado: no hay inversión L2 -> L1
            self._occupied -= 1
            self._free.add(slot)
            self._emit(EventKind.DONE, self._clock.now(), plan, ticket, slot=slot,
                       occupied=self._occupied)
        self._sem.release()  # liberar estrictamente antes de notify (sin despertar perdido)
        with self._cond:
            self._cond.notify_all()

    def wake(self):
        """Despierta a todos los que esperan para que vuelvan a verificar stop/running (lo usan stop y resume)."""
        with self._cond:
            self._cond.notify_all()

    def _dequeue(self, ticket):  # quien llama mantiene L1
        self._policy.remove(ticket)
        self._waiting = len(self._policy)

    def _emit(self, kind, now, plan, ticket, **fields):
        self._emitter.emit(kind, now, vehicle_id=plan.vehicle_id, ticket=ticket,
                           queue_len=self._waiting, **fields)
