"""Eventos de simulación inmutables y el emisor seguro para hilos que los publica."""
import enum
import threading
from dataclasses import dataclass
from typing import Optional


class EventKind(enum.Enum):
    STARTED = "STARTED"
    ARRIVED = "ARRIVED"
    PARKED = "PARKED"
    LEAVING = "LEAVING"
    DONE = "DONE"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"
    RESUMED = "RESUMED"
    SPEED = "SPEED"
    STOPPED = "STOPPED"
    RESET = "RESET"
    FINISHED = "FINISHED"


# Solo estos eventos llevan la ocupación real; cualquier otro tipo deja `occupied`
# con su valor por defecto (0), así que los consumidores no deben leer la ocupación de ellos.
OCCUPANCY_KINDS = frozenset({EventKind.PARKED, EventKind.DONE})


@dataclass(frozen=True)
class SimEvent:
    seq: int
    generation: int
    t: float  # segundos simulados
    kind: EventKind
    vehicle_id: Optional[int] = None
    ticket: Optional[int] = None
    slot: Optional[int] = None
    priority: Optional[int] = None
    occupied: int = 0
    queue_len: int = 0


class EventEmitter:
    """Asigna un número de seq a cada evento y lo pone en una cola.

    El Lock interno es una hoja en el orden de bloqueo (cond -> count_lock -> emitter):
    no se adquiere nada más mientras se lo mantiene, así que no puede formar parte de un ciclo.
    la asignación de seq y el encolado ocurren bajo el mismo Lock, así que el orden de la cola == orden de seq.
    """

    def __init__(self, out_queue, generation=0):
        self._queue = out_queue
        self._generation = generation
        self._lock = threading.Lock()
        self._seq = 0

    @property
    def generation(self):
        return self._generation

    def emit(self, kind, t, **fields):
        with self._lock:
            self._seq += 1
            event = SimEvent(seq=self._seq, generation=self._generation,
                             t=t, kind=kind, **fields)
            self._queue.put(event)
        return event
