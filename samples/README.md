# Salidas de ejemplo

Archivos CSV producidos por la línea de comandos headless mientras se construía y probaba el simulador. Se conservan como evidencia de ejecuciones reales y no los usan ni el código ni las pruebas.

Los eventos de los registros usan nombres fijos en inglés; la interfaz los muestra en español.

| Archivos | Comando utilizado |
|---|---|
| `sample_out.csv`, `sample_out.summary.csv` | `python3 -m parking --headless --seed 1 --capacity 2 --vehicles 5 --time-scale 0.02 --csv sample_out.csv` |
| `readme_check.csv`, `readme_check.summary.csv` | `python3 -m parking --headless --seed 42 --capacity 3 --vehicles 10 --time-scale 0.05 --csv readme_check.csv` |
| `verify_fix.csv`, `verify_fix.summary.csv`, `verify_fix.out` | `python3 -m parking --headless --seed 42 --capacity 3 --vehicles 10 --time-scale 0.02 --csv verify_fix.csv` (ejecutado después del lote de corrección de verificación; su utilización coincide con una reproducción independiente de PARKED/DONE) |

- `<nombre>.csv`: una fila por cada evento de la simulación (STARTED, ARRIVED, PARKED, LEAVING, DONE, FINISHED).
- `<nombre>.summary.csv`: las métricas (espera promedio y máxima, utilización, rendimiento, longitud máxima de la cola) como filas `metric,value`.

Los planes, el orden de admisión y los conteos son reproducibles para una semilla dada. Los valores de tiempo varían ligeramente entre ejecuciones porque dependen de la planificación real de los hilos.

En los CSV de eventos, la celda `occupied` queda vacía para los eventos que no incluyen un valor de ocupación (solo PARKED y DONE lo incluyen).
