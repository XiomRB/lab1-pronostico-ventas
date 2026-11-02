# lab1-pronostico-ventas

Producto de inteligencia artificial que transforma datos diarios de ventas en una recomendación semanal de pedido para un centro de distribución.

Proyecto académico en desarrollo.

Este repositorio no contiene datos ni modelos.

## Estado

El proyecto está en construcción por fases. Este README se completará con las instrucciones para reconstruir el producto desde cero.

## Entorno de desarrollo

Requisitos: Python 3.12, Git y `libgomp1`.

```bash
make install
make test
```

`make install` crea un entorno propio en `.venv` y aplica las constraints oficiales de Airflow 3.3.2.

## Datos y DVC

Git no guarda datos ni modelos. DVC es exclusivamente local y usa el remoto `../dvc-storage/lab1`, fuera del repositorio y de los volúmenes de Docker.

```bash
make prepare-remote
make verify-remote
```

El remoto local no sustituye a un respaldo: comparte disco con el proyecto. Para que otro equipo recupere los datos, el almacenamiento debe entregarse o respaldarse junto con el repositorio.

## Archivos de Kaggle y simulación

Coloca en `data/kaggle/` el ZIP de la competencia *Store Sales - Time Series Forecasting*, o sus CSV. Solo se usan `train.csv`, `stores.csv`, `holidays_events.csv`, `oil.csv` y `transactions.csv`.

```bash
make simulate
```

Genera la carga histórica en `data/historico/` y la bandeja en `data/bandeja/`. Si la entrada no cambió, no modifica nada.

El contrato de la bandeja está en [docs/contrato_bandeja.md](docs/contrato_bandeja.md). Las fechas se configuran en `config/simulacion.yaml`, la disponibilidad de las fuentes en `config/fuentes.yaml` y el horizonte en `config/modelo.yaml`. Los supuestos de disponibilidad son provisionales.

## Ingesta y control temporal

```bash
make ingest FECHA=2017-04-10
```

Procesa los archivos de la bandeja ya entregados en esa fecha lógica, sin modificar la bandeja. La fecha de entrega sale del nombre del archivo, nunca del reloj del sistema. Procesar día a día o de una vez da el mismo resultado, y repetir una ejecución no cambia nada.

| Situación | Resultado |
|---|---|
| Archivo válido | Se guarda en `data/almacen/` como una observación nueva |
| Archivo inválido | Va a `data/cuarentena/` con su motivo; las demás entregas continúan |
| Reentrega idéntica a la versión vigente | Se registra como duplicado |
| Corrección, también si vuelve a un contenido anterior | Se conservan todas las observaciones y queda vigente la última |
| Archivo tardío o fuente sin llegar | No es un error; el dato no existe hasta que se entrega |
| Archivo descubierto después de una ejecución que cubría su entrega | Se conserva su entrega original, pero solo se conoce desde su primera observación |
| Series faltantes, valor extremo o tienda nueva | Se acepta con una advertencia |
| Clave vacía o con formato no admitido | Va a cuarentena y no crea series nuevas |

Cada observación deja en `data/almacen/registro/` su secuencia, hash, estado, motivos, `fecha_entrega` y `conocido_desde`. Si dos versiones se conocen en la misma fecha, gana la de mayor secuencia. Las reglas de validación están en `config/validacion.yaml`.

`almacen.consulta.as_of(cfg, fuente, corte)` devuelve la última versión de cada registro conocida en una fecha de corte. Toda predicción debe construirse con esa consulta. Un dato ausente nunca se reemplaza por 0.

Cada ingesta informa además avisos de completitud según la frecuencia de cada fuente: ventas por series esperadas, transacciones de tiendas con ventas, y petróleo en días hábiles.

Las limitaciones conocidas están en [docs/deuda_tecnica.md](docs/deuda_tecnica.md).

## Modelado

```bash
make image
make evaluate
```

`make evaluate` compara el baseline y los candidatos de `config/modelo.yaml` dentro de la imagen de Airflow, con los mismos 8 cortes, en serie y bajo un límite de memoria. Las predicciones pueden diferir entre el host y la imagen, por lo que los resultados válidos son los de la imagen.

Las features de cada corte se construyen solo con `as_of`. Los cuantiles salen de residuos escalados de cortes posteriores al entrenamiento, y el pedido usa el cuantil crítico `Q* = Cu / (Cu + Co)` sobre la demanda acumulada del periodo. Los costos están en `config/costos.yaml` y son supuestos académicos.

El resultado está en [docs/evidencia/modelos/comparacion.md](docs/evidencia/modelos/comparacion.md).

## Versiones

| Paquete | Versión | Origen |
|---|---|---|
| Airflow | 3.3.2 | Última versión estable comprobada en la Fase 0 |
| Python | 3.12 | Versión de la imagen `apache/airflow:3.3.2-python3.12` |
| numpy | 2.5.3 | Constraints de Airflow |
| pandas | 3.0.5 | Constraints de Airflow |
| pyarrow | 25.0.1 | Constraints de Airflow |
| scikit-learn | 1.9.1 | Constraints de Airflow |
| scipy | 1.18.1 | Constraints de Airflow |
| joblib | 1.6.0 | Constraints de Airflow |
| PyYAML | 6.0.3 | Constraints de Airflow |
| lightgbm | 4.7.0 | Resuelta junto a las constraints |
| dvc | 3.67.1 | Resuelta junto a las constraints |
| pytest | 8.4.2 | Solo desarrollo; no figura en las constraints |

La compatibilidad se comprueba con `pip check` al instalar y en cada ejecución de CI.
