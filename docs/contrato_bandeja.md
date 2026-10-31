# Contrato de la bandeja

La bandeja simula el sistema de origen de la empresa. El flujo la lee y nunca la modifica.

**Estado:** contrato provisional. Las frecuencias, retrasos y anticipaciones son supuestos del proyecto, configurables y no confirmados por los docentes. Kaggle no publica cuándo estuvo disponible cada dato.

## Ubicación

La ruta por defecto es `data/bandeja`, definida en `config/simulacion.yaml`. La variable de entorno `BANDEJA_DIR` tiene prioridad y permite apuntar a otra bandeja.

El simulador no escribe en una carpeta con archivos que no generó él.

## Nombres de archivo

| Forma | Ejemplo | Fecha de entrega |
|---|---|---|
| Con entrega explícita | `ventas_2017-04-02__entrega_2017-04-09.csv` | La indicada en el nombre |
| Sin entrega | `ventas_2017-04-02.csv` | Fecha más el retraso de `config/fuentes.yaml` |

La disponibilidad se determina por la fecha de entrega, nunca por la hora del sistema. Puede haber varios archivos para la misma fecha y fuente: una entrega posterior representa una parte, una reentrega o una corrección.

## Fuentes y supuestos

| Fuente | Origen | Columnas | Frecuencia | Disponibilidad supuesta |
|---|---|---|---|---|
| `ventas` | `train.csv` | `id, date, store_nbr, family, sales, onpromotion` | Diaria | Día siguiente |
| `transacciones` | `transactions.csv` | `date, store_nbr, transactions` | Diaria | Dos días después |
| `promociones` | `train.csv` | `date, store_nbr, family, onpromotion` | Plan semanal | Cada domingo, cubre el horizonte del corte siguiente |
| `petroleo` | `oil.csv` | `date, dcoilwtico` | Días hábiles | Día hábil siguiente |
| `feriados` | `holidays_events.csv` | `date, type, locale, locale_name, description, transferred` | Por evento | 1 de enero; 14 días antes si es anuncio o traslado; el mismo día si es imprevisto |
| `tiendas` | `stores.csv` | `store_nbr, city, state, type, cluster` | Por cambio | Al abrir la tienda |

El nombre de un plan de `promociones` lleva su fecha de publicación. Las demás fuentes llevan la fecha de negocio.

En días sin operación no hay archivo: es una situación esperada, no un error.

## Periodo

El corte histórico y el fin de la bandeja se configuran en `config/simulacion.yaml`, y el horizonte en `config/modelo.yaml`. Con `fin_bandeja: null` se usa la última fecha de ventas de los archivos de Kaggle.

La carga histórica contiene los registros hasta el corte, con su columna `fecha_entrega`. También incluye los feriados futuros ya anunciados en esa fecha. Los precios del petróleo posteriores al fin no se entregan.

## Incidentes simulados

Se generan con semilla fija y quedan descritos en `data/historico/manifiesto_simulacion.json`.

| Incidente | Efecto |
|---|---|
| `archivo_tardio` | El archivo llega después de lo previsto |
| `archivo_parcial` | Una primera entrega incompleta y otra con el resto |
| `archivo_duplicado` | Reentrega idéntica |
| `correccion` | Valores erróneos en la primera entrega; la siguiente trae los reales |
| `dato_invalido` | Archivo con columna rota o venta negativa, seguido del correcto |
| `fuente_ausente` | El archivo no llega |
| `extremo_legitimo` | Se marca el valor real más alto, sin alterarlo |

Las alteraciones afectan solo a la primera entrega. Con excepción de los archivos ausentes, la última versión válida coincide con Kaggle.
