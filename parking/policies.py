"""Políticas de orden de la cola. El parqueadero las invoca mientras mantiene su Condition."""


class FifoPolicy:
    """Primero en llegar, primero en ser atendido: la cabeza es el turno más bajo (analogía de SO: FCFS)."""

    def __init__(self):
        self._tickets = {}  # turno -> vehicle_id

    def push(self, ticket, vehicle_id, priority, now):
        self._tickets[ticket] = vehicle_id

    def head(self, now):
        return min(self._tickets) if self._tickets else None

    def remove(self, ticket):
        self._tickets.pop(ticket, None)

    def __len__(self):
        return len(self._tickets)
