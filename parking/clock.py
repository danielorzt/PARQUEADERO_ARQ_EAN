"""Reloj de simulación: escalable y pausable. Los tiempos de evento están en segundos simulados."""
import threading
import time


class SimClock:
    """Convierte el tiempo monótono real en tiempo simulado.

    real_seconds = sim_seconds * time_scale. El reloj integra el tiempo transcurrido para que
    cambiar la escala o pausar nunca haga saltar el tiempo simulado.
    """

    def __init__(self, time_scale=1.0, source=time.monotonic):
        self._check_scale(time_scale)
        self._source = source
        self._lock = threading.Lock()
        self._scale = time_scale
        self._base_sim = 0.0
        self._base_real = source()
        self._paused = False

    @staticmethod
    def _check_scale(scale):
        if scale <= 0:
            raise ValueError("la escala de tiempo debe ser > 0")

    def _now_locked(self):
        if self._paused:
            return self._base_sim
        return self._base_sim + (self._source() - self._base_real) / self._scale

    def _rebase_locked(self):
        self._base_sim = self._now_locked()
        self._base_real = self._source()

    def now(self):
        with self._lock:
            return self._now_locked()

    def real_duration(self, sim_seconds):
        with self._lock:
            return sim_seconds * self._scale

    def pause(self):
        with self._lock:
            if not self._paused:
                self._rebase_locked()
                self._paused = True

    def resume(self):
        with self._lock:
            if self._paused:
                self._paused = False
                self._base_real = self._source()

    def set_scale(self, time_scale):
        self._check_scale(time_scale)
        with self._lock:
            self._rebase_locked()
            self._scale = time_scale

    def restart(self):
        """Reinicia el tiempo simulado a 0 desde este momento, conservando la escala y el estado de pausa."""
        with self._lock:
            self._base_sim = 0.0
            self._base_real = self._source()
