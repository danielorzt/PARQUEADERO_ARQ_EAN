"""Pruebas Tk de la aplicación; la clase se omite solo cuando no se puede crear una raíz Tk."""
import threading
import time
import unittest


_ROOT = None  # una raíz Tk oculta para todo el módulo (Tk 9 en macOS no tolera recrear raíces)


def _display_available():
    global _ROOT
    try:
        import tkinter
        _ROOT = tkinter.Tk()
        _ROOT.withdraw()
        return True
    except Exception:
        return False


_HAS_DISPLAY = _display_available()


def tearDownModule():
    if _ROOT is not None:
        _ROOT.destroy()


@unittest.skipUnless(_HAS_DISPLAY, "no display available")
class AppSmokeTests(unittest.TestCase):
    def setUp(self):
        import tkinter
        from dataclasses import replace
        from parking.config import SimConfig
        from parking.gui.app import ParkingApp
        self.root = tkinter.Toplevel(_ROOT)  # app.close() destruye solo esta ventana
        self.app = ParkingApp(self.root, replace(SimConfig(), num_vehicles=4, time_scale=0.01))

    def tearDown(self):
        self.app.close()

    def _pump_until(self, predicate, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.app.pump()
            self.app.render()
            self.root.update()
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def test_initial_buttons(self):
        self.assertFalse(self.app.buttons["start"].instate(["disabled"]))
        self.assertTrue(self.app.buttons["stop"].instate(["disabled"]))

    def test_start_runs_to_finish_and_lists_vehicles(self):
        self.app.on_start()
        self.assertTrue(self._pump_until(lambda: self.app.vm.state().phase == "finished"))
        self.assertEqual(len(self.app.tree.get_children()), 4)
        self.assertEqual(self.app.vm.state().occupied, 0)
        first = self.app.tree.get_children()[0]
        self.assertEqual(self.app.tree.item(first, "values")[1], "Terminado")
        self.assertEqual(self.app.phase_var.get(), "Estado: Finalizado")

    def test_invalid_capacity_shows_message(self):
        self.app.vars["capacity"].set("0")
        self.app.on_start()
        self.assertIn("capacidad", self.app.message_var.get().lower())
        self.assertEqual(self.app.vm.state().phase, "idle")

    def test_close_joins_workers_and_leaves_no_gen_threads(self):
        self.app.on_start()
        self.app.close()
        left = [t.name for t in threading.enumerate() if t.name.startswith("gen") and t.is_alive()]
        self.assertEqual(left, [])


    def test_metrics_panel_updates_from_events(self):
        self.app.on_start()
        self.assertTrue(self._pump_until(lambda: self.app.vm.state().phase == "finished"))
        self.assertEqual(self.app.metrics.summary().done, 4)
        self.assertIn("Cola máxima", self.app.metrics_vars["max_queue"].get())
        self.assertIn("Espera promedio", self.app.metrics_vars["avg_wait"].get())

    def test_export_csv_writes_every_event_and_reports_status(self):
        import csv
        import os
        import tempfile
        self.app.on_start()
        self.assertTrue(self._pump_until(lambda: self.app.vm.state().phase == "finished"))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gui.csv")
            self.app.csv_path_var.set(path)
            self.app.on_export()
            with open(path, newline="", encoding="utf-8") as fh:
                rows = list(csv.reader(fh))
            self.assertEqual(len(rows) - 1, len(self.app.event_log))
            self.assertTrue(os.path.exists(os.path.join(tmp, "gui.summary.csv")))
        self.assertIn("Se exportaron", self.app.message_var.get())

    def test_export_to_bad_path_shows_error_message(self):
        self.app.csv_path_var.set("/nonexistent-dir-xyz/out.csv")
        self.app.on_export()
        self.assertIn("no se puede escribir el archivo CSV", self.app.message_var.get())

    def test_reset_clears_metrics_and_event_log(self):
        self.app.on_start()
        self.assertTrue(self._pump_until(lambda: self.app.vm.state().phase == "finished"))
        self.app.on_reset()
        self.assertEqual(self.app.event_log, [])
        self.assertEqual(self.app.metrics.summary().done, 0)

    def _slot_cells(self):
        return {self.app.tree.item(i, "values")[0]: self.app.tree.item(i, "values")[3]
                for i in self.app.tree.get_children()}

    def test_spot_column_shows_the_one_based_slot_from_the_lot(self):
        from parking.events import EventKind, SimEvent
        gen = self.app.sim.generation
        self.app.queue.put(SimEvent(1, gen, 0.0, EventKind.ARRIVED, vehicle_id=1, ticket=0,
                                    queue_len=1))
        self.app.queue.put(SimEvent(2, gen, 0.0, EventKind.PARKED, vehicle_id=1, ticket=0,
                                    slot=1, occupied=1))
        self.app.queue.put(SimEvent(3, gen, 1.0, EventKind.PARKED, vehicle_id=2, ticket=1,
                                    slot=3, occupied=2))
        self.app.pump()
        self.app.render()
        self.assertEqual(self._slot_cells(), {"1": "1", "2": "3"})

    def test_config_fields_editable_again_after_finish_and_reset_applies_them(self):
        self.app.vars["time_scale"].set("0.01")
        self.app.on_start()
        self.assertTrue(self._pump_until(lambda: self.app.vm.state().phase == "finished"))
        self.assertTrue(all(not e.instate(["disabled"]) for e in self.app.entries))
        self.app.vars["capacity"].set("5")
        self.app.vars["vehicles"].set("2")
        self.app.on_reset()
        self.app.render()
        s = self.app.vm.state()
        self.assertEqual((s.capacity, s.phase), (5, "idle"))
        self.assertFalse(self.app.buttons["start"].instate(["disabled"]))
        self.app.on_start()
        self.assertTrue(self._pump_until(lambda: self.app.vm.state().phase == "finished"))
        self.assertEqual(self.app.metrics.summary().done, 2)

    def test_config_fields_disabled_while_running_and_editable_after_stop(self):
        self.app.vars["time_scale"].set("1")  # lo bastante lento para seguir en ejecución
        self.app.on_start()
        self.assertTrue(self._pump_until(lambda: self.app.vm.state().phase == "running"))
        self.assertTrue(all(e.instate(["disabled"]) for e in self.app.entries))
        self.app.on_stop()
        self.assertTrue(self._pump_until(lambda: self.app.vm.state().phase == "stopped"))
        self.assertTrue(all(not e.instate(["disabled"]) for e in self.app.entries))

    def test_arrival_and_park_inputs_exist_and_reach_the_config(self):
        for key in ("arrival_min", "arrival_max", "park_min", "park_max"):
            self.assertIn(key, self.app.vars)
        self.app.vars["arrival_min"].set("0.1")
        self.app.vars["arrival_max"].set("0.2")
        self.app.vars["park_min"].set("1.5")
        self.app.vars["park_max"].set("2.5")
        self.app.on_reset()
        cfg = self.app.sim._ctx.config
        self.assertEqual((cfg.arrival_gap, cfg.park_time), ((0.1, 0.2), (1.5, 2.5)))

    def test_invalid_range_shows_message_and_does_not_start(self):
        self.app.vars["park_min"].set("0")
        self.app.on_start()
        self.assertIn("estancia", self.app.message_var.get().lower())
        self.assertEqual(self.app.vm.state().phase, "idle")
        self.app.vars["park_min"].set("abc")
        self.app.on_start()
        self.assertIn("estancia", self.app.message_var.get().lower())

    def test_on_add_adds_a_vehicle_to_a_running_simulation(self):
        self.app.vars["time_scale"].set("0.05")  # ejecución de ~1 s: sigue activa al pulsar Agregar
        self.app.on_start()
        self.app.on_add()
        self.assertEqual(self.app.message_var.get(), "")
        self.assertTrue(self._pump_until(lambda: self.app.vm.state().phase == "finished"))
        self.assertEqual(self.app.metrics.summary().done, 5)
        self.assertEqual(len(self.app.tree.get_children()), 5)

    def test_on_add_after_finish_reports_run_finished(self):
        self.app.on_start()
        self.assertTrue(self._pump_until(lambda: self.app.vm.state().phase == "finished"))
        self.app.on_add()
        self.assertIn("ya finalizó", self.app.message_var.get())


if __name__ == "__main__":
    unittest.main()
