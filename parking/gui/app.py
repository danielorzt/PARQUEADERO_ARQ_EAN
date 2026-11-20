"""Interfaz Tk. Solo el hilo principal manipula los widgets; los trabajadores solo encolan SimEvent."""
import queue
import tkinter as tk
from tkinter import ttk

from parking.config import SimConfig
from parking.csv_export import CsvExportError, summary_path_for, write_events, write_summary
from parking.gui import ui_text, view_model
from parking.metrics import MetricsCollector
from parking.simulation import Simulation

TICK_MS = 50
MAX_EVENTS_PER_TICK = 200
CLOSE_JOIN_SECONDS = 1.0


class ParkingApp:
    def __init__(self, root, config=None):
        self.root = root
        root.title(ui_text.WINDOW_TITLE)
        config = config or SimConfig()
        self.queue = queue.Queue()
        self.sim = Simulation(config, self.queue)
        self.vm = view_model.ViewModel(config.capacity, self.sim.generation)
        self.metrics = MetricsCollector(config.capacity, self.sim.generation)
        self.event_log = []  # eventos de la generación actual, solo en el hilo principal
        self._after_id = None
        self._closed = False
        self._build_widgets(config)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.render()
        self._after_id = root.after(TICK_MS, self._tick)

    # ---- controles (widgets) -------------------------------------------------------
    def _build_widgets(self, config):
        frame = ttk.Frame(self.root, padding=8)
        frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.rowconfigure(4, weight=1)
        frame.columnconfigure(0, weight=1)

        inputs = ttk.LabelFrame(frame, text=ui_text.CONFIG_FRAME, padding=6)
        inputs.grid(row=0, column=0, sticky="ew")
        self.vars = {}
        self.entries = []
        fields = (("capacity", config.capacity),
                  ("vehicles", config.num_vehicles),
                  ("seed", config.seed),
                  ("time_scale", config.time_scale),
                  ("arrival_min", config.arrival_gap[0]),
                  ("arrival_max", config.arrival_gap[1]),
                  ("park_min", config.park_time[0]),
                  ("park_max", config.park_time[1]))
        for index, (key, value) in enumerate(fields):
            row, col = divmod(index, 4)  # dos filas de cuatro campos con etiqueta
            ttk.Label(inputs, text=ui_text.FIELD_LABELS[key]).grid(row=row, column=col * 2, padx=(6, 2), pady=2)
            self.vars[key] = tk.StringVar(value=str(value))
            entry = ttk.Entry(inputs, textvariable=self.vars[key], width=7)
            entry.grid(row=row, column=col * 2 + 1, pady=2)
            self.entries.append(entry)

        buttons = ttk.Frame(frame)
        buttons.grid(row=1, column=0, sticky="ew", pady=6)
        self.buttons = {}
        for name, handler in (("start", self.on_start),
                              ("add", self.on_add),
                              ("stop", self.on_stop),
                              ("reset", self.on_reset),
                              ("export", self.on_export)):
            self.buttons[name] = ttk.Button(buttons, text=ui_text.BUTTONS[name], command=handler)
            self.buttons[name].pack(side="left", padx=3)
        self.csv_path_var = tk.StringVar(value=ui_text.DEFAULT_CSV_PATH)
        ttk.Entry(buttons, textvariable=self.csv_path_var, width=24).pack(side="left", padx=3)

        self.free_var = tk.StringVar()
        self.occupied_var = tk.StringVar()
        self.queue_var = tk.StringVar()
        self.phase_var = tk.StringVar()
        counters = ttk.Frame(frame)
        counters.grid(row=2, column=0, sticky="ew")
        for var in (self.free_var, self.occupied_var, self.queue_var, self.phase_var):
            ttk.Label(counters, textvariable=var).pack(side="left", padx=8)

        panel = ttk.LabelFrame(frame, text=ui_text.METRICS_FRAME, padding=4)
        panel.grid(row=3, column=0, sticky="ew", pady=4)
        self.metrics_vars = {}
        for key in ("avg_wait", "max_wait", "utilization", "throughput", "max_queue"):
            self.metrics_vars[key] = tk.StringVar()
            ttk.Label(panel, textvariable=self.metrics_vars[key]).pack(side="left", padx=8)

        self.tree = ttk.Treeview(frame, columns=("vehicle", "state", "ticket", "slot"),
                                 show="headings", height=12)
        for col in ("vehicle", "state",
                    "ticket", "slot"):
            self.tree.heading(col, text=ui_text.COLUMN_TITLES[col])
            self.tree.column(col, width=90, anchor="center")
        self.tree.grid(row=4, column=0, sticky="nsew")

        self.message_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.message_var, foreground="red").grid(
            row=5, column=0, sticky="w")

    # ---- manejadores (no bloqueantes) -----------------------------------------
    def _launch(self, start):
        """Aplica la configuración editada a una ejecución nueva; la ejecuta ahora o la deja en reposo."""
        try:
            config = view_model.build_config({k: v.get() for k, v in self.vars.items()})
        except ValueError as exc:
            self.message_var.set(ui_text.MSG_INVALID_INPUT % exc)
            return
        self.message_var.set("")
        self.sim.reset(config)  # detiene la ejecución anterior sin esperar
        self.vm.reset(config.capacity, self.sim.generation)
        self.metrics.reset(config.capacity, self.sim.generation)
        self.event_log = []
        if start:
            self.sim.start()  # una ejecución reiniciada queda en reposo hasta iniciarla
        self.render()

    def on_start(self):
        self._launch(start=True)

    def on_reset(self):
        self._launch(start=False)  # vuelve a reposo: campos editables, Iniciar habilitado

    def on_add(self):
        if not self.sim.add_vehicle():
            self.message_var.set(ui_text.MSG_RUN_FINISHED)

    def on_stop(self):
        self.sim.stop()

    def on_export(self):
        path = self.csv_path_var.get().strip()
        if not path:
            self.message_var.set(ui_text.MSG_NEED_CSV_PATH)
            return
        try:
            write_events(path, self.event_log)
            summary_path = summary_path_for(path)
            write_summary(summary_path, self.metrics.summary())
        except CsvExportError as exc:
            self.message_var.set(str(exc))
            return
        self.message_var.set(ui_text.MSG_EXPORTED % (
            len(self.event_log), path, summary_path))

    # ---- bomba de eventos del hilo principal ------------------------------------------
    def pump(self):
        """Vacía hasta MAX_EVENTS_PER_TICK eventos; devuelve cuántos se leyeron."""
        drained = 0
        while drained < MAX_EVENTS_PER_TICK:
            try:
                event = self.queue.get_nowait()
            except queue.Empty:
                break
            drained += 1
            if self.vm.apply(event):  # descarta generaciones obsoletas
                self.metrics.apply(event)
                self.event_log.append(event)
        return drained

    def _tick(self):
        if self._closed:
            return
        if self.pump():
            self.render()
        self._after_id = self.root.after(TICK_MS, self._tick)

    def render(self):
        s = self.vm.state()
        self.free_var.set(ui_text.FREE % s.free)
        self.occupied_var.set(ui_text.OCCUPIED % (s.occupied, s.capacity))
        self.queue_var.set(ui_text.WAITING % s.queue_len)
        self.phase_var.set(ui_text.STATUS % ui_text.phase_name(s.phase))
        m = self.metrics.summary().rounded(2)
        self.metrics_vars["avg_wait"].set(ui_text.METRIC_TEMPLATES["avg_wait"] % m.avg_wait)
        self.metrics_vars["max_wait"].set(ui_text.METRIC_TEMPLATES["max_wait"] % m.max_wait)
        self.metrics_vars["utilization"].set(ui_text.METRIC_TEMPLATES["utilization"] % m.utilization)
        self.metrics_vars["throughput"].set(ui_text.METRIC_TEMPLATES["throughput"] % m.throughput)
        self.metrics_vars["max_queue"].set(ui_text.METRIC_TEMPLATES["max_queue"] % m.max_queue)
        for name, enabled in (("start", s.buttons.start), ("add", s.buttons.add),
                              ("stop", s.buttons.stop), ("reset", s.buttons.reset)):
            self.buttons[name].state(["!disabled"] if enabled else ["disabled"])
        for entry in self.entries:
            entry.state(["!disabled"] if s.buttons.edit_config else ["disabled"])
        self.tree.delete(*self.tree.get_children())
        for row in s.vehicles:
            self.tree.insert("", "end", values=(
                row.vehicle_id, ui_text.state_name(row.state),
                "" if row.ticket is None else row.ticket,
                "" if row.slot is None else row.slot))  # los espacios del parqueadero empiezan en 1

    # ---- cierre --------------------------------------------------------
    def close(self):
        """Detiene y une todos los trabajadores, luego destruye la ventana (idempotente)."""
        if self._closed:
            return
        self._closed = True
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
        self.sim.stop()
        self.sim.join(CLOSE_JOIN_SECONDS)
        self.root.destroy()


def main(auto_close_ms=None):
    root = tk.Tk()
    app = ParkingApp(root)
    if auto_close_ms is not None:
        root.after(auto_close_ms, app.close)
    root.mainloop()
    return 0
