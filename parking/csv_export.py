"""Exportación a CSV del registro de eventos y del resumen de métricas (módulo csv de la biblioteca estándar, sin GUI)."""
import csv
import dataclasses
import os

from parking.events import OCCUPANCY_KINDS

EVENT_HEADER = ("seq", "generation", "t", "kind", "vehicle_id", "ticket", "slot",
                "priority", "occupied", "queue_len")
SUMMARY_HEADER = ("metric", "value")


class CsvExportError(Exception):
    """Se lanza con un mensaje legible cuando no se puede escribir un archivo CSV."""


def summary_path_for(events_path):
    """Archivo hermano para el resumen: run.csv -> run.summary.csv."""
    base, ext = os.path.splitext(events_path)
    return "%s.summary%s" % (base, ext or ".csv")


def _cell(value):
    if value is None:
        return ""
    return value.value if hasattr(value, "value") else value


def _write(path, header, rows):
    try:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerows(rows)
    except OSError as exc:
        raise CsvExportError("no se puede escribir el archivo CSV '%s': %s" % (path, exc.strerror or exc)) from exc


def _event_row(ev):
    row = [_cell(getattr(ev, name)) for name in EVENT_HEADER]
    if ev.kind not in OCCUPANCY_KINDS:  # el 0 por defecto allí significa "desconocido", no "parqueadero vacío"
        row[EVENT_HEADER.index("occupied")] = ""
    return row


def write_events(path, events):
    """Encabezado y una fila por evento, en el orden (seq) dado.

    `occupied` se llena solo para PARKED/DONE (los eventos que lo llevan).
    """
    _write(path, EVENT_HEADER, (_event_row(ev) for ev in events))


def write_summary(path, summary):
    """Archivo de dos columnas metric,value con cada campo de MetricsSummary."""
    _write(path, SUMMARY_HEADER,
           ([f.name, _cell(getattr(summary, f.name))] for f in dataclasses.fields(summary)))
