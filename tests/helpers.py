"""Utilidades compartidas: vaciar una cola de eventos y verificar invariantes en el registro reproducido."""
import queue
import threading

from parking.events import EventKind

WAIT = 10.0  # cota superior generosa para las esperas de Event; nunca es una demora fija


def drain(q):
    events = []
    while True:
        try:
            events.append(q.get_nowait())
        except queue.Empty:
            return events


def gen_threads():
    """Hilos activos creados por el simulador (con nombre gen<N>-...)."""
    return [t for t in threading.enumerate() if t.name.startswith("gen")]


def check_log(testcase, events, capacity):
    """Reproduce los eventos en orden de seq y verifica los invariantes principales."""
    seqs = [e.seq for e in events]
    testcase.assertEqual(seqs, sorted(seqs), "queue order must equal seq order")
    occupied = 0
    for e in events:
        if e.kind is EventKind.PARKED:
            occupied += 1
        elif e.kind is EventKind.DONE:
            occupied -= 1
        if e.kind in (EventKind.PARKED, EventKind.DONE):
            testcase.assertEqual(e.occupied, occupied)
            testcase.assertTrue(0 <= occupied <= capacity,
                                "occupied %d outside [0, %d]" % (occupied, capacity))
    parked = [e.ticket for e in events if e.kind is EventKind.PARKED]
    testcase.assertEqual(parked, sorted(parked), "PARKED order must equal ticket order")
    slots = {}
    for e in events:
        if e.kind is EventKind.PARKED:
            testcase.assertNotIn(e.slot, slots.values(), "slot reused while occupied")
            slots[e.vehicle_id] = e.slot
        elif e.kind is EventKind.DONE:
            slots.pop(e.vehicle_id, None)


def collect_until(q, events, predicate, timeout=WAIT):
    """Extrae eventos de q hacia `events` hasta que predicate(events) se cumpla (o venza el tiempo)."""
    import time
    deadline = time.monotonic() + timeout
    while not predicate(events):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        try:
            events.append(q.get(timeout=min(remaining, 0.05)))
        except queue.Empty:
            pass
    return True


def count(events, kind):
    return len([e for e in events if e.kind is kind])
