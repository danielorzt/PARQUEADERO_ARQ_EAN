"""Generación determinista de planes de vehículos a partir de un RNG con semilla."""
from dataclasses import dataclass

VIP = 0
NORMAL = 1


@dataclass(frozen=True)
class VehiclePlan:
    vehicle_id: int
    arrival_time: float  # segundos simulados desde el inicio
    park_time: float  # segundos simulados estacionado
    priority: int = NORMAL


def generate_plans(config, rng, start_id=1, start_time=0.0):
    """Devuelve config.num_vehicles planes extraídos de `rng`.

    Cada vehículo consume siempre exactamente tres sorteos (intervalo, tiempo de estancia, sorteo VIP),
    en ese orden, así que cambiar vip_ratio nunca desplaza los demás valores.
    """
    plans = []
    arrival = start_time
    for offset in range(config.num_vehicles):
        arrival += rng.uniform(*config.arrival_gap)
        park_time = rng.uniform(*config.park_time)
        vip_roll = rng.random()
        priority = VIP if vip_roll < config.vip_ratio else NORMAL
        plans.append(VehiclePlan(start_id + offset, arrival, park_time, priority))
    return plans
