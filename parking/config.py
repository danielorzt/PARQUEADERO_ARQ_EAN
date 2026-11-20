"""Configuración inmutable de la simulación y presets."""
from dataclasses import dataclass

POLICIES = ("fifo", "priority")


@dataclass(frozen=True)
class SimConfig:
    """Parámetros de una ejecución de simulación. Los valores de tiempo están en segundos simulados."""

    capacity: int = 3
    num_vehicles: int = 10
    arrival_gap: tuple = (0.5, 2.0)
    park_time: tuple = (2.0, 5.0)
    seed: int = 1
    policy: str = "fifo"
    time_scale: float = 1.0  # segundos reales por segundo simulado
    vip_ratio: float = 0.2
    aging_rate: float = 0.1
    poll: float = 0.05  # segundos reales entre verificaciones de stop/pausa

    def validate(self):
        """Lanza ValueError cuando algún campo está fuera de rango."""
        if self.capacity < 1:
            raise ValueError("la capacidad debe ser >= 1")
        if self.num_vehicles < 0:
            raise ValueError("el número de vehículos debe ser >= 0")
        _check_range("intervalo de llegada", self.arrival_gap, allow_zero=True)
        _check_range("tiempo de estancia", self.park_time, allow_zero=False)
        if self.time_scale <= 0:
            raise ValueError("la escala de tiempo debe ser > 0")
        if self.policy not in POLICIES:
            raise ValueError("la política debe ser una de %s" % (POLICIES,))
        if not 0.0 <= self.vip_ratio <= 1.0:
            raise ValueError("la proporción VIP debe estar en [0, 1]")
        if self.aging_rate < 0:
            raise ValueError("la tasa de envejecimiento debe ser >= 0")
        if self.poll <= 0:
            raise ValueError("el intervalo de sondeo debe ser > 0")


def _check_range(name, value, allow_zero):
    low, high = value
    if low < 0 or (low == 0 and not allow_zero):
        raise ValueError("%s: el límite inferior está fuera de rango" % name)
    if high < low:
        raise ValueError("%s: el mínimo debe ser <= máximo" % name)


PRESETS = {
    "small": SimConfig(capacity=2, num_vehicles=6),
    "default": SimConfig(),
    "rush-hour": SimConfig(capacity=3, num_vehicles=20, arrival_gap=(0.1, 0.5)),
    "vip-mix": SimConfig(capacity=3, num_vehicles=15, policy="priority", vip_ratio=0.3),
}
