# lab1-pronostico-ventas

Producto de inteligencia artificial que transforma datos diarios de ventas en una recomendación semanal de pedido para un centro de distribución.

Proyecto académico en desarrollo.

Este repositorio no contiene datos ni modelos.

## Inicio rápido

Requisitos: Linux o WSL 2, Git, GNU Make, OpenSSL, y Docker con Compose. Se recomiendan al menos 4 GB de memoria libres para Docker. La primera construcción de la imagen necesita acceso a Docker Hub, PyPI, GitHub y los repositorios de Debian.

```bash
git clone https://github.com/XiomRB/lab1-pronostico-ventas.git lab1
cd lab1
mkdir -p data/kaggle
cp /ruta/a/store-sales-time-series-forecasting.zip data/kaggle/
make up
```

`make up` genera los secretos en `.env`, construye la imagen, prepara el remoto DVC en `../dvc-storage/lab1`, genera el histórico y la bandeja, y levanta Airflow en http://localhost:8080. El usuario es `airflow` y la clave es `_AIRFLOW_WWW_USER_PASSWORD` en `.env`.

Los DAGs arrancan sin pausa y el orquestador `operacion_diaria` procesa solo el periodo configurado. No requiere intervención manual. `make down` detiene los servicios.

### Periodo de evaluación

El periodo se configura en `.env`, con `LAB1_INICIO` y `LAB1_FIN`, y el corte histórico en `config/simulacion.yaml`.

Para usar una bandeja externa con el formato de [docs/contrato_bandeja.md](docs/contrato_bandeja.md), define `BANDEJA_HOST=/ruta/absoluta` en `.env`. La carpeta se monta en solo lectura y no se ejecuta el simulador.

### Backfill y reproceso

```bash
docker compose --env-file .env -f airflow/docker-compose.yaml exec airflow-scheduler \
  airflow backfill create --dag-id operacion_diaria \
  --from-date 2017-08-01T00:00:00 --to-date 2017-08-07T23:59:00 \
  --reprocess-behavior none --max-active-runs 1
```

`--to-date` debe incluir la hora. `--reprocess-behavior none` cubre periodos nuevos, y `failed` o `completed` repiten corridas ya ejecutadas. Solo puede haber un backfill activo por DAG.

## Resultados

| Salida | Ubicación |
|---|---|
| Pronósticos y pedidos | `data/publicado/corte=.../rev=N/` |
| Estado de cada publicación | `data/estado_publicaciones/` |
| Seguimiento del desempeño | `reportes/seguimiento.md` y `data/seguimiento/` |
| Comparación de modelos | [docs/evidencia/modelos/comparacion.md](docs/evidencia/modelos/comparacion.md) |
| Decisiones técnicas | [DECISIONES.md](DECISIONES.md) |

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

Comandos de DVC del proyecto:

| Comando | Uso |
|---|---|
| `dvc add <ruta>` | Registrar datos, modelos o publicaciones |
| `dvc push` | Copiar al remoto local |
| `dvc pull` | Traer desde el remoto local |
| `dvc status` | Ver cambios locales |
| `dvc status -c --json` | Comprobar la sincronía: solo `{}` significa sincronizado |
| `dvc checkout` | Alinear los archivos con los `.dvc` de un commit |
| `dvc repro` | Reproducir el pipeline de `dvc.yaml` |

Cada publicación crea un commit en la rama local `publicaciones`, con su etiqueta `pub/<corte>-r<N>`.

### Recuperar y reproducir un pronóstico pasado

```bash
python scripts/recuperar_pronostico.py --corte 2017-04-03 --revision 1 --destino ../recuperado
cd ../recuperado
docker run --rm -u "$(id -u):0" -e PYTHONPATH=/opt/lab1/src -e OMP_NUM_THREADS=4 \
  -v "$PWD":/opt/lab1 -w /opt/lab1 lab1-pronostico:3.3.2 \
  python scripts/reproducir_pronostico.py --corte 2017-04-03 --revision 1
```

La evidencia está en [docs/evidencia/recuperacion/](docs/evidencia/recuperacion/).

### Respaldo

```bash
make backup-dvc DESTINO=/ruta/en/otro/medio
make restore-dvc ARCHIVO=/ruta/en/otro/medio/dvc-storage-lab1-....tar
```

La restauración verifica el SHA-256 y no sobrescribe un remoto existente.

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

## Publicación

`python -m pronostico_ventas.publicacion --corte AAAA-MM-DD` publica el pronóstico diario con P10, P50 y P90, y el pedido sugerido en `data/publicado/corte=.../rev=N/`, junto a un manifiesto con el commit, los hashes de datos, modelo y configuración, el corte, el horizonte y la revisión.

Una publicación no se modifica. Con `--reprocesar-en` se crea una revisión nueva con los datos corregidos conocidos en esa fecha y el modelo de la publicación original. Si los datos de ventas están demasiado atrasados, la publicación se omite y queda registrado el motivo.

Sin datos de inventario, el pedido representa la necesidad bruta del periodo. Las series sin ventas en 28 días y las tiendas sin ventas en 7 días reciben pedido 0 con una marca.

Una publicación solo queda `RESPALDADA` si el remoto es un montaje real, existe su centinela, `dvc push` termina bien, `dvc status -c --json` devuelve `{}` y los hashes de sus objetos coinciden. El estado de cada publicación está en `data/estado_publicaciones/`.

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
