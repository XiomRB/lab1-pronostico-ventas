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
