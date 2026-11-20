"""Ejecutor de línea de comandos sin GUI: imprime una cronología y un resumen determinista.

No debe importar tkinter (ni nada de parking.gui): la CLI debe funcionar
en máquinas sin Tk instalado.

Los campos del resumen (plan, orden de admisión, conteos) dependen solo de la
semilla y de la política, así que dos ejecuciones con los mismos argumentos
imprimen resúmenes idénticos. La cronología muestra tiempos reales y es solo
informativa.
"""
import argparse
import contextlib
import dataclasses
import queue
import random
import sys

from parking.csv_export import CsvExportError, summary_path_for, write_events, write_summary
from parking.config import POLICIES, PRESETS, SimConfig
from parking.events import OCCUPANCY_KINDS, EventKind
from parking.metrics import MetricsCollector
from parking.plans import VIP, generate_plans
from parking.simulation import Simulation

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130
SUMMARY_MARKER = "== Resumen =="
_SLICE = 0.2  # segundos reales por finished.wait() para atender Ctrl-C con rapidez
METRIC_DIGITS = 2  # las métricas de tiempo se redondean; los conteos son exactos
_JOIN_TIMEOUT = 5.0  # segundos reales de espera de los hilos al terminar la ejecución


class _SpanishHelpFormatter(argparse.HelpFormatter):
    """Usa el prefijo 'uso: ' en lugar de 'usage: ' (solo API pública)."""

    def add_usage(self, usage, actions, groups, prefix=None):
        if prefix is None:
            prefix = "uso: "
        super().add_usage(usage, actions, groups, prefix)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python3 -m parking --headless",
        formatter_class=_SpanishHelpFormatter,
        description="Ejecuta la simulación del parqueadero sin interfaz gráfica.")
    parser.add_argument("--headless", action="store_true",
                        help="ejecuta sin interfaz gráfica (obligatorio en este punto de entrada)")
    parser.add_argument("--preset", choices=sorted(PRESETS),
                        help="parte de un preset con nombre; las opciones explícitas lo reemplazan")
    parser.add_argument("--capacity", type=int, help="número de espacios del parqueadero (>= 1)")
    parser.add_argument("--vehicles", type=int, dest="num_vehicles",
                        help="número de vehículos a generar (>= 0)")
    parser.add_argument("--arrival-gap", type=float, nargs=2, metavar=("MIN", "MAX"),
                        help="segundos simulados entre llegadas")
    parser.add_argument("--park-time", type=float, nargs=2, metavar=("MIN", "MAX"),
                        help="segundos simulados que cada vehículo permanece estacionado")
    parser.add_argument("--seed", type=int, help="semilla del generador aleatorio; la misma semilla da el mismo plan")
    parser.add_argument("--policy", choices=POLICIES, help="política de admisión")
    parser.add_argument("--vip-ratio", type=float, help="proporción de vehículos VIP en [0, 1]")
    parser.add_argument("--time-scale", type=float,
                        help="segundos reales por segundo simulado (> 0)")
    parser.add_argument("--csv", metavar="PATH", dest="csv_path",
                        help="escribe el registro de eventos en PATH y el resumen de métricas "
                             "en PATH con el sufijo .summary")
    return parser


def parse_config(argv):
    """Construye un SimConfig validado a partir de argv. Lanza SystemExit (argparse) o ValueError."""
    return config_from_args(build_parser().parse_args(argv))


def config_from_args(args):
    """Aplica el preset, luego las opciones explícitas, y después valida. Lanza ValueError."""
    overrides = {}
    for name in ("capacity", "num_vehicles", "seed", "policy", "vip_ratio", "time_scale"):
        value = getattr(args, name)
        if value is not None:
            overrides[name] = value
    if args.arrival_gap is not None:
        overrides["arrival_gap"] = tuple(args.arrival_gap)
    if args.park_time is not None:
        overrides["park_time"] = tuple(args.park_time)
    base = PRESETS[args.preset] if args.preset else SimConfig()
    config = dataclasses.replace(base, **overrides)
    config.validate()
    return config


def main(argv=None, out=None, err=None):
    """Punto de entrada. Devuelve el código de salida del proceso; nunca llama a sys.exit por sí mismo."""
    out = out if out is not None else sys.stdout
    err = err if err is not None else sys.stderr
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    with contextlib.redirect_stderr(err):
        try:
            args = parser.parse_args(argv)
        except SystemExit as exc:
            return int(exc.code or 0)
    try:
        config = config_from_args(args)
    except ValueError as exc:
        parser.print_usage(err)
        err.write("%s: error: %s\n" % (parser.prog, exc))
        return EXIT_USAGE
    return run_headless(config, out, err, csv_path=args.csv_path)


def run_headless(config, out, err, csv_path=None):
    """Ejecuta una simulación completa e imprime su cronología y su resumen."""
    events_queue = queue.Queue()
    try:
        sim = Simulation(config, events_queue)
    except ImportError:
        # make_policy importa PriorityPolicy de forma diferida; puede no estar disponible.
        err.write("error: la política '%s' no está disponible en esta compilación\n" % config.policy)
        return EXIT_USAGE
    sim.start()
    try:
        while not sim.finished.wait(_SLICE):
            pass
    except KeyboardInterrupt:
        sim.stop()
        sim.join(_JOIN_TIMEOUT)
        return EXIT_INTERRUPTED
    sim.join(_JOIN_TIMEOUT)
    events = _drain(events_queue)
    plans = generate_plans(config, random.Random(config.seed))
    metrics = MetricsCollector(config.capacity)
    for ev in events:
        metrics.apply(ev)
    _write_timeline(events, out)
    # Las métricas de tiempo varían con la planificación real de hilos, así que van en su propio
    # bloque ANTES del resumen determinista (que es idéntico para semillas iguales).
    _write_metrics(metrics.summary().rounded(METRIC_DIGITS), out)
    _write_summary(config, plans, events, out)
    if csv_path is not None:
        return _export_csv(csv_path, events, metrics.summary(), out, err)
    return EXIT_OK


def _export_csv(path, events, summary, out, err):
    summary_path = summary_path_for(path)
    try:
        write_events(path, events)
        write_summary(summary_path, summary)
    except CsvExportError as exc:
        err.write("error: %s\n" % exc)
        return EXIT_ERROR
    out.write("CSV de eventos: %s\nCSV de resumen: %s\n" % (path, summary_path))
    return EXIT_OK


def _write_metrics(m, out):
    out.write("== Métricas (segundos simulados, tiempos redondeados a %d decimales) ==\n"
              % METRIC_DIGITS)
    out.write("Espera promedio: %.2f s\n" % m.avg_wait)
    out.write("Espera máxima: %.2f s\n" % m.max_wait)
    out.write("Utilización: %.2f\n" % m.utilization)
    out.write("Rendimiento: %.2f vehículos/s\n" % m.throughput)
    out.write("Cola máxima: %d\n" % m.max_queue)


def _drain(events_queue):
    events = []
    while True:
        try:
            events.append(events_queue.get_nowait())
        except queue.Empty:
            return events


def _cell(value):
    return "-" if value is None else str(value)


def _write_timeline(events, out):
    out.write("== Cronología ==\n")
    occupied = 0  # seguimiento: solo PARKED/DONE llevan el valor real; los demás tipos usan 0 por defecto
    for ev in events:
        if ev.kind in OCCUPANCY_KINDS:
            occupied = ev.occupied
        out.write("%8.2fs  %-9s vehicle=%-3s ticket=%-3s slot=%-2s occupied=%d\n" % (
            ev.t, ev.kind.value, _cell(ev.vehicle_id), _cell(ev.ticket),
            _cell(ev.slot), occupied))


def _write_summary(config, plans, events, out):
    out.write("%s\n" % SUMMARY_MARKER)
    out.write("Configuración: seed=%d capacity=%d vehicles=%d policy=%s time_scale=%r\n" % (
        config.seed, config.capacity, config.num_vehicles, config.policy, config.time_scale))
    out.write("Plan (exacto, a partir de la semilla):\n")
    for plan in plans:
        out.write("  id=%d arrival=%r park=%r priority=%s\n" % (
            plan.vehicle_id, plan.arrival_time, plan.park_time,
            "VIP" if plan.priority == VIP else "NORMAL"))
    admitted = [ev.vehicle_id for ev in events if ev.kind is EventKind.PARKED]
    out.write("Orden de admisión: %s\n" % " ".join(str(v) for v in admitted))
    counts = {kind: sum(1 for ev in events if ev.kind is kind) for kind in
              (EventKind.ARRIVED, EventKind.PARKED, EventKind.DONE, EventKind.CANCELLED)}
    out.write("Conteos:\n")
    out.write("  Llegados: %d\n" % counts[EventKind.ARRIVED])
    out.write("  Estacionados: %d\n" % counts[EventKind.PARKED])
    out.write("  Terminados: %d\n" % counts[EventKind.DONE])
    out.write("  Cancelados: %d\n" % counts[EventKind.CANCELLED])
    complete = counts[EventKind.DONE] == config.num_vehicles
    out.write("Resultado: %s\n" % ("completo" if complete else "incompleto"))
