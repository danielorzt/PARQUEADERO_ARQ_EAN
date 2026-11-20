"""Módulo de textos de visualización: completitud de los mapas y guardia contra literales de UI en inglés."""
import ast
import os
import re
import unittest

from parking.gui import view_model

_GUI_DIR = os.path.dirname(view_model.__file__)

FORBIDDEN = frozenset({"Start", "Stop", "Reset", "Capacity", "Vehicles", "Seed", "Free",
                       "Waiting", "Invalid", "Status", "max", "State", "Ticket", "Spot",
                       "Vehicle"})
# Lista blanca exacta: opciones y claves de Tk, claves de campos, botones y métricas, estados y fases internos.
ALLOWED = frozenset({
    "", "!disabled", "disabled", "!selected",
    "nsew", "ew", "w", "left", "end", "center", "red", "headings",
    "WM_DELETE_WINDOW", "__main__",
    "capacity", "vehicles", "seed", "time_scale", "arrival_min", "arrival_max",
    "park_min", "park_max", "arrival", "park", "_min", "_max",
    "start", "add", "stop", "reset", "export",
    "vehicle", "state", "ticket", "slot",
    "avg_wait", "max_wait", "utilization", "throughput", "max_queue",
    "WAITING", "PARKED", "LEAVING", "DONE", "CANCELLED",
    "idle", "running", "paused", "stopped", "finished",
    "_",
})
_KEY = re.compile(r"!?[A-Za-z_][A-Za-z0-9_]*")


def _docstring_nodes(tree):
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(
                    body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                skip.add(id(body[0].value))
    return skip


def violations(source):
    """Devuelve los literales de cadena (sin docstrings) que no están en ALLOWED."""
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    return sorted({n.value for n in ast.walk(tree)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)
                   and id(n) not in skip and n.value not in ALLOWED})


class UiTextMapTests(unittest.TestCase):
    def test_maps_are_complete_and_unknown_keys_are_returned_raw(self):
        from parking.gui import ui_text
        self.assertEqual(set(ui_text.STATE_NAMES), set(view_model._VEHICLE_STATE.values()))
        self.assertEqual(set(ui_text.PHASE_NAMES), set(view_model._PHASE.values()) | {"idle"})
        self.assertEqual(ui_text.state_name("DONE"), "Terminado")
        self.assertEqual(ui_text.phase_name("finished"), "Finalizado")
        self.assertEqual(ui_text.state_name("NOPE"), "NOPE")
        self.assertEqual(ui_text.phase_name("nope"), "nope")


class NoEnglishLiteralGuardTests(unittest.TestCase):
    def test_allow_list_is_exact_and_gui_sources_have_no_stray_literals(self):
        for entry in ALLOWED:
            self.assertTrue(entry == "" or _KEY.fullmatch(entry), entry)
        self.assertFalse(ALLOWED & FORBIDDEN)
        self.assertEqual(violations('ttk.Button(text="Start")'), ["Start"])
        for name in ("app.py", "view_model.py"):
            with open(os.path.join(_GUI_DIR, name), encoding="utf-8") as fh:
                self.assertEqual(violations(fh.read()), [], name)


if __name__ == "__main__":
    unittest.main()
