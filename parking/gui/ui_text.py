"""Textos de visualización en español para la GUI. Puro: sin importar tkinter ni parking.*."""
WINDOW_TITLE = "Simulador de Parqueadero"
CONFIG_FRAME = "Configuración"
METRICS_FRAME = "Métricas (segundos simulados)"
DEFAULT_CSV_PATH = "parking_events.csv"

FIELD_LABELS = {"capacity": "Capacidad", "vehicles": "Vehículos", "seed": "Semilla",
                "time_scale": "Escala de tiempo (s reales/s sim.)",
                "arrival_min": "Llegada mín. (s)", "arrival_max": "máx.",
                "park_min": "Estancia mín. (s)", "park_max": "máx."}
BUTTONS = {"start": "Iniciar", "add": "Agregar vehículo", "stop": "Detener",
           "reset": "Reiniciar", "export": "Exportar CSV"}
COLUMN_TITLES = {"vehicle": "Vehículo", "state": "Estado", "ticket": "Turno",
                 "slot": "Espacio"}

FREE = "Espacios libres: %d"
OCCUPIED = "Espacios ocupados: %d / %d"
WAITING = "En espera: %d"
STATUS = "Estado: %s"
METRIC_TEMPLATES = {"avg_wait": "Espera promedio: %.2f s",
                    "max_wait": "Espera máxima: %.2f s",
                    "utilization": "Utilización: %.2f",
                    "throughput": "Rendimiento: %.2f /s",
                    "max_queue": "Cola máxima: %d"}

# Claves internas (en inglés) -> nombres para mostrar.
STATE_NAMES = {"WAITING": "Esperando", "PARKED": "Estacionado", "LEAVING": "Saliendo",
               "DONE": "Terminado", "CANCELLED": "Cancelado"}
PHASE_NAMES = {"idle": "En reposo", "running": "En ejecución", "paused": "En pausa",
               "stopped": "Detenido", "finished": "Finalizado"}

FIELD_NAMES = {"capacity": "capacidad", "vehicles": "vehículos", "seed": "semilla",
               "time_scale": "escala de tiempo", "arrival": "intervalo de llegada",
               "park": "tiempo de estancia"}
RANGE_MIN = " mínimo"
RANGE_MAX = " máximo"

MSG_NOT_A_NUMBER = "%s debe ser un número válido"
MSG_CAPACITY_MIN = "la capacidad debe ser >= 1"
MSG_INVALID_INPUT = "Entrada no válida: %s"
MSG_RUN_FINISHED = "La simulación ya finalizó; Reiniciar permite empezar de nuevo."
MSG_NEED_CSV_PATH = "Primero se debe indicar una ruta CSV."
MSG_EXPORTED = "Se exportaron %d eventos a %s (+ %s)"


def state_name(key):
    return STATE_NAMES.get(key, key)


def phase_name(key):
    return PHASE_NAMES.get(key, key)
