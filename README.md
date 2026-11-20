# Simulador de Parqueadero en Python

Simulación de un parqueadero escrita únicamente con la biblioteca estándar de
Python. Cada vehículo es un hilo que compite por un número limitado de espacios.
El proyecto muestra cómo conceptos clásicos de los sistemas operativos
(semáforos contadores, mutex, monitores, planificación FCFS, prevención de
interbloqueo) aparecen en un programa concreto.

El núcleo de la simulación no depende de ninguna interfaz gráfica. Una ventana
Tkinter y un ejecutor de línea de comandos sin interfaz (headless) consumen el
mismo flujo de eventos.

## Idioma

Los eventos de los registros usan nombres fijos en inglés; la interfaz los muestra en español.

Los identificadores del código, las banderas de la línea de comandos, los nombres
de eventos (`ARRIVED`, `PARKED`, `LEAVING`, `DONE`, `CANCELLED`, `STARTED`,
`FINISHED`, etc.) y los encabezados de los CSV son el vocabulario técnico fijo de
los registros, por lo que no se traducen. La interfaz gráfica y la salida de la
línea de comandos sí están en español.

## Requisitos

- Python 3.15 (desarrollado y probado con 3.15.2). Sin paquetes de terceros.
- Tkinter, necesario solo para la interfaz gráfica. El ejecutor headless y las
  pruebas no lo importan. En macOS con Homebrew se instala la fórmula
  correspondiente:

  ```sh
  brew install python-tk@3.15
  ```

## Cómo ejecutar

Todos los comandos se ejecutan desde la raíz del proyecto (el directorio que
contiene `parking/`).

Interfaz gráfica (modo por defecto cuando no se indica `--headless`):

```sh
python3 -m parking
```

Modo headless, que imprime una cronología, las métricas y un resumen:

```sh
python3 -m parking --headless --seed 42 --capacity 3 --vehicles 10 --time-scale 0.05
```

Modo headless con exportación a CSV. `run.csv` recibe el registro de eventos y
`run.summary.csv` recibe las métricas:

```sh
python3 -m parking --headless --seed 42 --capacity 3 --vehicles 10 --time-scale 0.05 --csv run.csv
```

Pruebas (`unittest` estándar):

```sh
python3 -m unittest discover -s tests -v
```

Al momento de escribir, la suite ejecuta 138 pruebas y todas pasan.

La salida headless tiene tres secciones: `== Cronología ==` (un evento por
línea), `== Métricas (segundos simulados, tiempos redondeados a 2 decimales) ==`
(Espera promedio, Espera máxima, Utilización, Rendimiento, Cola máxima) y
`== Resumen ==` (configuración, plan exacto a partir de la semilla, Orden de
admisión, Conteos de Llegados, Estacionados, Terminados y Cancelados, y
Resultado).

Opciones del modo headless: `--preset {small,default,rush-hour,vip-mix}`,
`--capacity N`, `--vehicles N`, `--arrival-gap MIN MAX`, `--park-time MIN MAX`
(segundos simulados), `--seed N`, `--policy {fifo,priority}`, `--vip-ratio R`,
`--time-scale S` (segundos reales por segundo simulado), `--csv PATH`. Las
banderas explícitas tienen prioridad sobre el preset. Códigos de salida: 0 éxito,
1 error al escribir el CSV, 2 uso incorrecto o política no disponible, 130
interrupción con Ctrl-C.

Los mensajes de uso y de error están en español y empiezan con `uso:` o
`error:`. Por ejemplo, con `--capacity 0`:

```text
python3 -m parking --headless: error: la capacidad debe ser >= 1
```

### Controles de la interfaz gráfica

- Campos de configuración: Capacidad, Vehículos, Semilla, Escala de tiempo,
  Llegada (mínimo y máximo) y Estancia (mínimo y máximo), en segundos
  simulados. Se pueden editar mientras la ejecución está En reposo, Detenido o
  Finalizado, y quedan bloqueados mientras está En ejecución o En pausa. Los
  valores no válidos muestran un mensaje y no se inicia nada.
- Botones Iniciar, Agregar vehículo, Detener y Reiniciar. Reiniciar aplica la
  configuración editada y vuelve al estado En reposo (no inicia la
  simulación); se debe pulsar Iniciar para ejecutarla.
- Contadores Espacios libres, Espacios ocupados y En espera, y el Estado de la
  ejecución (En reposo, En ejecución, En pausa, Detenido, Finalizado).
- Panel de métricas: Espera promedio, Espera máxima, Utilización, Rendimiento y
  Cola máxima.
- Tabla de vehículos con las columnas Vehículo, Estado, Turno y Espacio. Los
  estados son Esperando, Estacionado, Saliendo, Terminado y Cancelado.
- Exportar CSV: escribe los eventos y el resumen de la ejecución actual en la
  ruta escrita en el cuadro de texto. No abre un diálogo de archivos. En el CSV
  de eventos, la columna `occupied` se llena solo en las filas PARKED y DONE (los
  eventos que la incluyen) y queda vacía en las demás.

## Mapa de módulos

| Ruta | Responsabilidad |
|------|-----------------|
| `parking/__main__.py` | Punto de entrada. Dirige al ejecutor headless o a la interfaz gráfica. |
| `parking/config.py` | `SimConfig` (dataclass inmutable), validación, `PRESETS`. |
| `parking/events.py` | `SimEvent` (inmutable), `EventKind`, `EventEmitter` (números de secuencia, lock hoja). |
| `parking/clock.py` | `SimClock`: tiempo simulado escalado y pausable. |
| `parking/plans.py` | `VehiclePlan` y `generate_plans(config, rng)`. Determinista para una semilla. |
| `parking/policies.py` | Políticas de cola. `FifoPolicy` está implementada. |
| `parking/lot.py` | `ParkingLot`: el monitor de admisión (Condition, Semaphore, lock del contador). |
| `parking/vehicle.py` | Cuerpo del hilo de vehículo: llegar, esperar, estacionar, salir. |
| `parking/simulation.py` | Controlador `Simulation`, hilo despachador, generaciones de ejecución (Reiniciar). |
| `parking/metrics.py` | `MetricsCollector`: cálculo puro a partir de los eventos. |
| `parking/csv_export.py` | Escritores de CSV para los eventos y el resumen. |
| `parking/headless.py` | Ejecutor de línea de comandos. Nunca importa Tkinter. |
| `parking/gui/view_model.py` | Modelo de vista puro que convierte los eventos en estado para mostrar. |
| `parking/gui/app.py` | Interfaz Tkinter. Solo el hilo principal toca los widgets. |
| `tests/` | Suite `unittest`, un módulo por cada módulo fuente más pruebas de integración. |

## Diseño de concurrencia

Hilos: un hilo despachador (`gen{g}-dispatcher`) y un hilo por vehículo
(`gen{g}-vehicle-{id}`). Los vehículos nunca se comunican directamente entre
sí. Comparten el `ParkingLot` y publican `SimEvent` en una `queue.Queue`. Un
único consumidor (el hilo principal de Tk o el ciclo headless) vacía esa cola.

La admisión funciona así. Un vehículo se admite solo cuando se cumplen las tres
condiciones:

1. La ejecución no está en pausa (el Event `running` está activado).
2. Su turno (ticket) es la cabeza de la cola de la política.
3. `Semaphore.acquire(blocking=False)` tiene éxito.

En caso contrario, el vehículo espera en la Condition con un tiempo límite
(`poll`, 50 ms por defecto) y vuelve a comprobar.

| Primitiva | Función |
|-----------|---------|
| `threading.Condition` (`_cond`) | Compuerta de turnos y monitor. Los vehículos en espera duermen en ella. Cada cambio de estado llama a `notify_all`. |
| `threading.Semaphore(capacity)` | Cuenta los espacios libres. Solo se adquiere sin bloqueo y únicamente mientras se tiene `_cond`. |
| `threading.Lock` (`_count_lock`) | Protege el contador de ocupación y el conjunto de números de espacio libres. |
| `threading.Event` `stop` | Los vehículos en espera se cancelan (CANCELLED). Los vehículos estacionados salen antes de tiempo por la ruta `finally`. |
| `threading.Event` `running` | Compuerta de pausa. La pausa lo desactiva; reanudar y detener lo activan. |
| Número de generación | Reiniciar lo incrementa. A los hilos viejos se les ordena detenerse, pero no se espera su finalización (join). Los consumidores descartan los eventos de generaciones obsoletas. |

**Orden de locks.** `_cond` (L1), luego `_count_lock` (L2), luego el lock del
emisor (L3, una hoja). Un hilo nunca adquiere un lock de número menor mientras
tiene uno de número mayor. `leave()` libera `_cond` antes de tomar
`_count_lock`, por lo que no hay inversión. El semáforo se libera antes de
`notify_all`, de modo que no se puede perder un despertar.

**Por qué un `threading.Semaphore` simple no basta.** Un semáforo cuenta los
espacios pero no decide quién los obtiene. El docstring de CPython para
`Semaphore.acquire` indica que los hilos bloqueados pueden despertarse "at
random, so the order in which blocked threads are awakened should not be relied
on" (al azar, por lo que no se debe confiar en el orden de despertar). Como la
ruta rápida toma un permiso libre sin pasar por una cola, un hilo recién llegado
puede quedarse con un espacio antes que un hilo que espera hace más tiempo
(barging). Por eso, el orden de llegada (FCFS, primero en llegar, primero en ser
atendido) exige una cola explícita, que aquí es la compuerta de turnos. El
semáforo solo cuenta espacios. La corrección FIFO incorporada en CPython
(gh-90155) se aplica a `asyncio.Semaphore`, no a `threading.Semaphore`.

## Conceptos de sistemas operativos en este proyecto

| Concepto de SO | Dónde aparece aquí | Notas |
|----------------|--------------------|-------|
| Hilo / proceso | Vehículo = hilo | Los hilos comparten un espacio de direcciones, por lo que el estado del parqueadero necesita locks. Procesos de SO separados necesitarían IPC. |
| Recurso finito | Espacios de parqueo (`capacity`) | Limitado, compartido, nunca debe comprometerse en exceso. |
| Semáforo contador (P/V) | `Semaphore(capacity)`; `acquire` sin bloqueo es P, `release` es V | Cuenta las instancias del recurso. |
| Mutex / sección crítica | `_count_lock` alrededor de `_occupied` y `_free` | Protege las actualizaciones de leer-modificar-escribir. |
| Monitor | `ParkingLot` con `_cond` | Lock más variable de condición, con revisiones en `while`. |
| Cola de listos / de espera | Turnos en `FifoPolicy`; los hilos duermen en `_cond` | |
| Planificación FCFS | `FifoPolicy`: la cabeza es el turno más bajo | El orden de llegada es igual al orden de admisión. |
| Despachador / planificador de largo plazo | El hilo despachador emite turnos en el orden del plan | Orden de llegada determinista. |
| Señales, suspender y reanudar | Event `running` (pausa), Event `stop` | La pausa está en la API del núcleo. La interfaz aún no tiene control para ella. |
| Terminación de procesos | Token de generación en Reiniciar; `stop` cancela a los que esperan | Las finalizaciones obsoletas se ignoran. |
| Estados de proceso | ARRIVED = esperando, PARKED = en ejecución con un recurso, LEAVING, DONE = terminado | Nombres usados por el modelo de vista. |
| Efecto convoy | Con FIFO, una cabeza lenta retrasa a todos los que están detrás | No se mitiga en la versión actual. |
| Inanición (starvation) | Posible en la planificación por prioridad sin envejecimiento | La política de prioridad aún no está implementada. |
| Condición de carrera | Un `occupied += 1` sin lock puede perder actualizaciones | Se previene con `_count_lock`. Una demostración está planificada, no construida. |
| Interbloqueo (deadlock) | Cuatro condiciones de Coffman (ver abajo) | Prevenido por diseño, no evitado. |

### Interbloqueo: las cuatro condiciones de Coffman

El interbloqueo necesita las cuatro condiciones a la vez. Este diseño rompe cada
una:

| Condición | Cómo se rompe aquí |
|-----------|--------------------|
| Exclusión mutua | Se mantiene. Un espacio aloja un vehículo, y el contador requiere acceso exclusivo. |
| Retener y esperar | Un vehículo que espera un espacio no retiene ningún otro recurso. El permiso se adquiere sin bloqueo y cada vehículo tiene como máximo un permiso. |
| Sin expropiación | No hace falta romperla: un espacio lo libera solo su dueño, en un bloque `finally`, en la salida normal o al detener. |
| Espera circular | Orden total de locks `_cond` -> `_count_lock` -> lock del emisor. `leave()` nunca anida locks en orden inverso. |

Esto es **prevención** de interbloqueo (la estructura descarta un ciclo). No es
**evitación** (avoidance) en el sentido del algoritmo del banquero, que
requeriría conocer de antemano las necesidades de recursos de cada vehículo.
Además, toda espera bloqueante tiene tiempo límite (`cond.wait` con `poll`,
`stop.wait`), así que una señal perdida retrasa a un vehículo pero no puede
colgar el programa.

### Hilo frente a proceso

Los vehículos son hilos, no procesos del SO. Esto mantiene el estado compartido
en un solo espacio de direcciones, y por eso se necesitan los locks. El mismo
ciclo de vida podría ejecutarse con procesos, pero tendrían que intercambiar el
estado mediante mensajes o memoria compartida.

## Determinismo

- La semilla determina el plan completo (tiempos de llegada, tiempos de
  estancia, banderas VIP) y se imprime en el resumen.
- Con FIFO, el orden de admisión es igual al orden de turnos, y los turnos los
  emite un único despachador en el orden del plan. Por eso el Orden de
  admisión y los Conteos (Llegados, Estacionados, Terminados, Cancelados) son
  los mismos para los mismos argumentos.
- Las marcas de tiempo de la cronología, los números de espacio y las métricas de
  tiempo (esperas, utilización, rendimiento) dependen de la planificación real
  de los hilos y varían ligeramente entre ejecuciones. Las métricas de tiempo se
  redondean a dos decimales. Se imprimen en un bloque separado antes del resumen
  determinista, de modo que el resumen se pueda comparar directamente.
- El tiempo simulado está desacoplado del tiempo real mediante `--time-scale`.
  Los tiempos de los eventos son segundos simulados, así que las métricas no
  dependen de la velocidad elegida.

## Limitaciones conocidas y pendientes

- La política de prioridad (VIP primero, con envejecimiento) aún no está
  implementada. `--policy priority` y el preset `vip-mix` terminan por ahora con
  código 2 y el mensaje "error: la política 'priority' no está disponible en
  esta compilación". Con FIFO, la bandera VIP se genera pero no tiene efecto
  sobre la admisión.
- La interfaz no tiene controles de pausa ni de velocidad. La API del núcleo
  admite pausar y reanudar.
- Aún no hay vista animada del parqueadero ni gráfico de utilización.
- Aún no hay demostración de interbloqueo ni de condición de carrera.
- La interfaz se verifica con pruebas de Tk (usan una ventana raíz oculta y solo
  se omiten cuando no se puede crear una raíz de Tk) y con ejecuciones manuales,
  no con comprobaciones visuales automáticas.

## Informe y video de demostración

- Informe escrito: `report/report.pdf` (versión completa en formato APA 7) y
  `report/report_2p.pdf` (versión breve de 2 páginas).
- Video explicativo (3:27): https://youtu.be/OiavsLwP6i0
- Código fuente: https://github.com/danielorzt/PARQUEADERO_ARQ_EAN
