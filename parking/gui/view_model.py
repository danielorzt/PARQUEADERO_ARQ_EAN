"""View-model puro: pliega SimEvent en el estado de visualización. Nunca importa tkinter."""
from dataclasses import dataclass, field

from parking.config import SimConfig
from parking.events import OCCUPANCY_KINDS, EventKind
from parking.gui import ui_text


@dataclass(frozen=True)
class VehicleRow:
    vehicle_id: int
    state: str
    ticket: object = None
    slot: object = None


@dataclass(frozen=True)
class Buttons:
    start: bool
    add: bool
    stop: bool
    reset: bool
    edit_config: bool = False  # campos de configuración editables (no mientras una ejecución está activa)


@dataclass(frozen=True)
class ViewState:
    capacity: int
    occupied: int
    free: int
    queue_len: int
    phase: str  # idle | running | paused | stopped | finished
    vehicles: list = field(default_factory=list)
    buttons: Buttons = None


_VEHICLE_STATE = {
    EventKind.ARRIVED: "WAITING",
    EventKind.PARKED: "PARKED",
    EventKind.LEAVING: "LEAVING",
    EventKind.DONE: "DONE",
    EventKind.CANCELLED: "CANCELLED",
}
# Los eventos del parqueadero llevan el conteo de espera en vivo; LEAVING de los hilos de vehículo y los eventos de control
# dejan queue_len en su valor por defecto 0, así que no deben sobrescribirlo.
_QUEUE_KINDS = frozenset({EventKind.ARRIVED, EventKind.PARKED,
                          EventKind.CANCELLED, EventKind.DONE})
_PHASE = {
    EventKind.STARTED: "running",
    EventKind.PAUSED: "paused",
    EventKind.RESUMED: "running",
    EventKind.STOPPED: "stopped",
    EventKind.FINISHED: "finished",
}


def _buttons(phase):
    active = phase in ("running", "paused")
    return Buttons(start=phase == "idle", add=active, stop=active, reset=True,
                   edit_config=not active)


class ViewModel:
    """Pliegue de eventos con un solo consumidor; se descartan los eventos de otras generaciones."""

    def __init__(self, capacity, generation=0):
        self.reset(capacity, generation)

    def reset(self, capacity, generation):
        self._capacity = capacity
        self._generation = generation
        self._occupied = 0
        self._queue_len = 0
        self._phase = "idle"
        self._rows = {}

    def apply(self, event):
        """Pliega un evento; devuelve False cuando pertenece a una generación obsoleta."""
        if event.generation != self._generation:
            return False
        if event.kind in OCCUPANCY_KINDS:
            self._occupied = event.occupied
        if event.kind in _QUEUE_KINDS:
            self._queue_len = event.queue_len
        phase = _PHASE.get(event.kind)
        if phase:
            self._phase = phase
        state = _VEHICLE_STATE.get(event.kind)
        if state and event.vehicle_id is not None:
            old = self._rows.get(event.vehicle_id)
            slot = event.slot if event.slot is not None else (old.slot if old else None)
            self._rows[event.vehicle_id] = VehicleRow(
                event.vehicle_id, state, event.ticket, slot)
        return True

    def state(self):
        rows = [self._rows[k] for k in sorted(self._rows)]
        return ViewState(self._capacity, self._occupied, self._capacity - self._occupied,
                         self._queue_len, self._phase, rows, _buttons(self._phase))


def _parse(fields, key, caster, label):
    try:
        return caster(str(fields[key]).strip())
    except (KeyError, ValueError):
        raise ValueError(ui_text.MSG_NOT_A_NUMBER % label)


def _parse_range(fields, prefix, label, default):
    """Lee `<prefix>_min`/`<prefix>_max`; si faltan ambos se usa el valor por defecto de SimConfig."""
    if prefix + "_min" not in fields and prefix + "_max" not in fields:
        return default
    return (_parse(fields, prefix + "_min", float, label + ui_text.RANGE_MIN),
            _parse(fields, prefix + "_max", float, label + ui_text.RANGE_MAX))


def build_config(fields):
    """Construye un SimConfig validado a partir de textos sin procesar; ValueError lleva un mensaje para el usuario."""
    capacity = _parse(fields, "capacity", int, ui_text.FIELD_NAMES["capacity"])
    if capacity < 1:
        raise ValueError(ui_text.MSG_CAPACITY_MIN)
    defaults = SimConfig()
    cfg = SimConfig(
        capacity=capacity,
        num_vehicles=_parse(fields, "vehicles", int, ui_text.FIELD_NAMES["vehicles"]),
        seed=_parse(fields, "seed", int, ui_text.FIELD_NAMES["seed"]),
        time_scale=_parse(fields, "time_scale", float, ui_text.FIELD_NAMES["time_scale"]),
        arrival_gap=_parse_range(fields, "arrival", ui_text.FIELD_NAMES["arrival"], defaults.arrival_gap),
        park_time=_parse_range(fields, "park", ui_text.FIELD_NAMES["park"], defaults.park_time),
    )
    cfg.validate()
    return cfg
