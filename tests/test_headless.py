import csv
import io
import os
import tempfile
import random
import subprocess
import sys
import unittest
from pathlib import Path

from parking.config import PRESETS
from parking.headless import main, parse_config
from parking.plans import generate_plans

ROOT = Path(__file__).resolve().parent.parent
# Tiempo real rápido (0.01 s por segundo simulado) mantiene cada ejecución muy por debajo de un segundo.
FAST = ["--seed", "42", "--capacity", "3", "--vehicles", "10", "--time-scale", "0.01"]
SUMMARY_MARKER = "== Resumen =="


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, out, err)
    return code, out.getvalue(), err.getvalue()


def summary_of(text):
    return text.split(SUMMARY_MARKER, 1)[1]


class ArgumentTests(unittest.TestCase):
    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        code = main(argv, out, err)
        return code, out.getvalue(), err.getvalue()

    def test_non_positive_capacity_exits_two_with_usage(self):
        code, out, err = self.run_cli(["--capacity", "0"])
        self.assertEqual(code, 2)
        self.assertIn("uso:", err)
        self.assertIn("la capacidad debe ser >= 1", err)
        self.assertEqual(out, "", "no timeline may be printed for invalid args")

    def test_unparseable_number_exits_two_with_usage(self):
        code, _, err = self.run_cli(["--capacity", "abc"])
        self.assertEqual(code, 2)
        self.assertIn("uso:", err)

    def test_inverted_range_is_rejected(self):
        code, _, err = self.run_cli(["--park-time", "5", "2"])
        self.assertEqual(code, 2)
        self.assertIn("tiempo de estancia: el mínimo debe ser <= máximo", err)

    def test_unknown_policy_is_rejected_by_argparse(self):
        code, _, err = self.run_cli(["--policy", "bogus"])
        self.assertEqual(code, 2)
        self.assertIn("uso:", err)


class RunTests(unittest.TestCase):
    def test_successful_run_exits_zero_and_prints_timeline(self):
        code, out, err = run(FAST)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        for kind in ("STARTED", "ARRIVED", "PARKED", "DONE", "FINISHED"):
            self.assertIn(kind, out)

    def test_timeline_occupied_is_tracked_not_the_default_zero(self):
        # Los eventos ARRIVED/LEAVING no llevan ocupación; la cronología debe mostrar el
        # valor acumulado (estacionados menos terminados hasta el momento), nunca un 0 engañoso.
        _, out, _ = run(FAST)
        timeline = out.split("== Cronología ==\n", 1)[1].split("== Métricas", 1)[0]
        occupied = 0
        checked = 0
        for line in timeline.strip().splitlines():
            kind = line.split()[1]
            if kind == "PARKED":
                occupied += 1
            elif kind == "DONE":
                occupied -= 1
            self.assertEqual(int(line.rsplit("occupied=", 1)[1]), occupied, line)
            if kind in ("ARRIVED", "LEAVING") and occupied:
                checked += 1
        self.assertGreater(checked, 0, "no ARRIVED/LEAVING line with a non-zero occupancy")

    def test_same_seed_twice_gives_identical_summary(self):
        _, first, _ = run(FAST)
        _, second, _ = run(FAST)
        self.assertIn(SUMMARY_MARKER, first)
        self.assertEqual(summary_of(first), summary_of(second))

    def test_different_seed_gives_different_plan(self):
        _, first, _ = run(FAST)
        other = [*FAST[:1], "43", *FAST[2:]]
        _, second, _ = run(other)
        self.assertNotEqual(summary_of(first), summary_of(second))

    def test_admission_order_follows_ticket_order_under_fifo(self):
        _, out, _ = run(FAST)
        expected = "Orden de admisión: " + " ".join(str(i) for i in range(1, 11))
        self.assertIn(expected, summary_of(out))

    def test_counts_reflect_a_complete_run(self):
        _, out, _ = run(FAST)
        summary = summary_of(out)
        for line in ("Llegados: 10", "Estacionados: 10", "Terminados: 10", "Cancelados: 0"):
            self.assertIn(line, summary)

    def test_plan_values_are_printed_exactly_from_the_seed(self):
        config = parse_config(["--seed", "42", "--capacity", "3", "--vehicles", "10"])
        plans = generate_plans(config, random.Random(config.seed))
        _, out, _ = run(FAST)
        summary = summary_of(out)
        for plan in plans:
            self.assertIn(repr(plan.arrival_time), summary)
            self.assertIn(repr(plan.park_time), summary)

    def test_zero_vehicles_finishes_immediately(self):
        code, out, _ = run(["--vehicles", "0", "--time-scale", "0.01"])
        self.assertEqual(code, 0)
        self.assertIn("Llegados: 0", summary_of(out))


class EntryPointTests(unittest.TestCase):
    def test_python_m_parking_headless_runs_end_to_end(self):
        argv = [sys.executable, "-m", "parking", "--headless", "--seed", "42",
                "--capacity", "3", "--vehicles", "10", "--time-scale", "0.01"]
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(SUMMARY_MARKER, result.stdout)
        self.assertIn("Orden de admisión: 1 2 3 4 5 6 7 8 9 10", result.stdout)

    def test_python_m_parking_headless_invalid_args_exit_two(self):
        argv = [sys.executable, "-m", "parking", "--headless", "--capacity", "0"]
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 2)
        self.assertIn("uso:", result.stderr)


class PolicyAvailabilityTests(unittest.TestCase):
    def test_priority_policy_reports_clean_error_until_unit_six(self):
        code, out, err = run(["--policy", "priority", "--vehicles", "1",
                              "--time-scale", "0.01"])
        self.assertEqual(code, 2)
        self.assertIn("la política 'priority' no está disponible en esta compilación", err)
        self.assertEqual(out, "")


class IsolationTests(unittest.TestCase):
    def test_core_cli_never_imports_tkinter(self):
        probe = ("import sys, parking.headless; "
                 "sys.exit(1 if 'tkinter' in sys.modules or "
                 "'parking.gui' in sys.modules else 0)")
        result = subprocess.run([sys.executable, "-c", probe], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


class ConfigTests(unittest.TestCase):
    def test_preset_supplies_the_whole_configuration(self):
        self.assertEqual(parse_config(["--preset", "small"]), PRESETS["small"])

    def test_explicit_flags_override_preset_fields(self):
        config = parse_config(["--preset", "small", "--capacity", "4"])
        self.assertEqual(config.capacity, 4)
        self.assertEqual(config.num_vehicles, PRESETS["small"].num_vehicles)

    def test_ranges_become_float_tuples(self):
        config = parse_config(["--arrival-gap", "0.1", "0.5", "--park-time", "1", "2"])
        self.assertEqual(config.arrival_gap, (0.1, 0.5))
        self.assertEqual(config.park_time, (1.0, 2.0))

    def test_vehicles_flag_maps_to_num_vehicles(self):
        self.assertEqual(parse_config(["--vehicles", "7"]).num_vehicles, 7)

    def test_seed_and_policy_flags(self):
        config = parse_config(["--seed", "42", "--policy", "fifo"])
        self.assertEqual((config.seed, config.policy), (42, "fifo"))

    def test_defaults_match_simconfig_when_no_flags(self):
        self.assertEqual(parse_config([]).capacity, 3)



class MetricsAndCsvTests(unittest.TestCase):
    def test_metrics_block_is_printed_and_replaces_the_hook(self):
        code, out, _ = run(FAST)
        self.assertEqual(code, 0)
        self.assertNotIn("no está disponible en esta compilación", out)
        metrics = out.split("== Métricas", 1)[1].split(SUMMARY_MARKER, 1)[0]
        for label in ("Espera promedio:", "Espera máxima:", "Utilización:", "Rendimiento:",
                      "Cola máxima:"):
            self.assertIn(label, metrics)

    def test_timing_values_are_rounded_to_two_decimals(self):
        _, out, _ = run(FAST)
        line = [l for l in out.splitlines() if l.startswith("Espera promedio:")][0]
        number = line.split(":", 1)[1].split()[0]
        self.assertLessEqual(len(number.split(".")[1]), 2)

    def test_deterministic_summary_stays_identical_with_metrics_present(self):
        _, first, _ = run(FAST)
        _, second, _ = run(FAST)
        self.assertEqual(summary_of(first), summary_of(second))

    def test_zero_vehicles_metrics_are_zero(self):
        code, out, _ = run(["--vehicles", "0", "--time-scale", "0.01"])
        self.assertEqual(code, 0)
        self.assertIn("Espera promedio: 0.00", out)
        self.assertIn("Cola máxima: 0", out)

    def test_csv_flag_writes_events_and_summary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "run.csv")
            code, out, err = run(FAST + ["--csv", path])
            self.assertEqual((code, err), (0, ""))
            with open(path, newline="", encoding="utf-8") as fh:
                rows = list(csv.reader(fh))
            kinds = [r[3] for r in rows[1:]]
            self.assertEqual(kinds.count("PARKED"), 10)
            self.assertEqual(kinds.count("DONE"), 10)
            # una fila CSV por línea de la cronología
            timeline = out.split("== Cronología ==\n", 1)[1].split("== Métricas", 1)[0]
            self.assertEqual(len(rows) - 1, len(timeline.strip().splitlines()))
            with open(os.path.join(tmp, "run.summary.csv"), newline="", encoding="utf-8") as fh:
                summary = {r[0]: r[1] for r in list(csv.reader(fh))[1:]}
            self.assertEqual(summary["done"], "10")
            self.assertIn(path, out)

    def test_unwritable_csv_path_reports_error_without_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "no-such-dir", "run.csv")
            code, out, err = run(FAST + ["--csv", bad])
        self.assertEqual(code, 1)
        self.assertIn("no se puede escribir el archivo CSV", err)
        self.assertIn("no-such-dir", err)
        self.assertIn(SUMMARY_MARKER, out)  # la ejecución igualmente informó el resumen

if __name__ == "__main__":
    unittest.main()
