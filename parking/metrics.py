"""Métricas puras, sin GUI, derivadas de SimEvent (sin hilos ni Locks).

Un único hilo consumidor entrega los eventos en orden de cola (seq) mediante apply(); el colector
es, por construcción, de un solo hilo. Los tiempos están en segundos simulados, así que
los resultados no dependen de la configuración de velocidad.

  espera      = PARKED.t - ARRIVED.t por vehículo (los cancelados no aportan muestra)
  utilización = integral(occupied dt) / (capacidad * transcurrido)
  rendimiento = vehículos DONE por segundo simulado de tiempo transcurrido
  cola máxima = pico de queue_len observado en cualquier evento
"""
import dataclasses
from dataclasses import dataclass

from parking.events import OCCUPANCY_KINDS, EventKind


@dataclass(frozen=True)
class MetricsSummary:
    avg_wait: float
    max_wait: float
    utilization: float
    throughput: float
    max_queue: int
    parked: int
    done: int
    cancelled: int = 0
    elapsed: float = 0.0

    def rounded(self, digits=2):
        """Redondea las métricas de tiempo; los conteos y max_queue permanecen exactos."""
        return dataclasses.replace(
            self,
            avg_wait=round(self.avg_wait, digits),
            max_wait=round(self.max_wait, digits),
            utilization=round(self.utilization, digits),
            throughput=round(self.throughput, digits),
            elapsed=round(self.elapsed, digits))


class MetricsCollector:
    def __init__(self, capacity, generation=None):
        self.reset(capacity, generation)

    def reset(self, capacity, generation=None):
        """Olvida todo; generation=None acepta eventos de cualquier generación."""
        self._capacity = capacity
        self._generation = generation
        self._arrived = {}
        self._waits = []
        self._occupied = 0
        self._last_t = None
        self._start_t = None
        self._area = 0.0
        self._max_queue = 0
        self._done = 0
        self._cancelled = 0

    def apply(self, event):
        """Consume un evento; devuelve False (y lo ignora) cuando está obsoleto."""
        if self._generation is not None and event.generation != self._generation:
            return False
        t = event.t
        if self._last_t is None:
            self._start_t = self._last_t = t
        else:
            # t se registra justo antes del Lock del emisor, así que puede retrasarse un poco.
            self._area += self._occupied * max(0.0, t - self._last_t)
            self._last_t = max(self._last_t, t)
        if event.kind in OCCUPANCY_KINDS:  # otros tipos llevan el valor por defecto occupied=0
            self._occupied = event.occupied
        self._max_queue = max(self._max_queue, event.queue_len)
        kind = event.kind
        if kind is EventKind.ARRIVED:
            self._arrived[event.vehicle_id] = t
        elif kind is EventKind.PARKED:
            arrived = self._arrived.pop(event.vehicle_id, None)
            if arrived is not None:
                self._waits.append(max(0.0, t - arrived))
        elif kind is EventKind.DONE:
            self._done += 1
        elif kind is EventKind.CANCELLED:
            self._arrived.pop(event.vehicle_id, None)
            self._cancelled += 1
        return True

    def summary(self):
        elapsed = 0.0 if self._last_t is None else self._last_t - self._start_t
        waits = self._waits
        utilization = (self._area / (self._capacity * elapsed)
                       if elapsed > 0 and self._capacity > 0 else 0.0)
        return MetricsSummary(
            avg_wait=sum(waits) / len(waits) if waits else 0.0,
            max_wait=max(waits) if waits else 0.0,
            utilization=utilization,
            throughput=self._done / elapsed if elapsed > 0 else 0.0,
            max_queue=self._max_queue,
            parked=len(waits),
            done=self._done,
            cancelled=self._cancelled,
            elapsed=elapsed)
