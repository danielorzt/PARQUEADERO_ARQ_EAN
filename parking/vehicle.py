"""Cuerpo del hilo de vehículo: ARRIVED -> espera -> PARKED -> LEAVING -> DONE (ciclo de vida del proceso)."""
from parking.events import EventKind


def vehicle_worker(plan, ticket, ctx):
    """Ejecuta un vehículo. `ctx` provee lot, clock, emitter, stop y poll.

    El espacio se libera en `finally` solo si realmente se adquirió, así que una detención
    en cualquier momento (esperando, estacionado o entre ambos) nunca deja fugas ni libera dos veces.
    """
    slot = None
    try:
        slot = ctx.lot.await_admission(ticket)
        if slot is None:
            return  # detenido mientras esperaba; el parqueadero ya emitió CANCELLED
        _park(plan, ctx)
        ctx.emitter.emit(EventKind.LEAVING, ctx.clock.now(), vehicle_id=plan.vehicle_id,
                         ticket=ticket, slot=slot)
    finally:
        if slot is not None:
            ctx.lot.leave(ticket, slot)


def _park(plan, ctx):
    """Permanece estacionado durante plan.park_time segundos simulados; se puede pausar y detener.

    El tiempo simulado se congela en pausa, así que el tiempo restante nunca disminuye y
    el bucle solo vuelve a sondear. Esperar sobre el Event de stop da una pausa temporizada e interrumpible.
    """
    started = ctx.clock.now()
    while not ctx.stop.is_set():
        remaining = plan.park_time - (ctx.clock.now() - started)
        if remaining <= 0:
            return
        ctx.stop.wait(min(ctx.poll, ctx.clock.real_duration(remaining)))
