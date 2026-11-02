# Decisiones técnicas y de producto

Este documento describe las decisiones del producto: qué se decidió, qué alternativas se consideraron y por qué se eligió cada solución. Los valores marcados como supuestos son configurables y no provienen de los datos ni de requisitos del curso.

## Producto

| Decisión | Alternativas | Justificación |
|---|---|---|
| Pronóstico diario por tienda y familia, con horizonte de 14 días | Horizonte fijo por el enunciado; pronóstico semanal | El horizonte es del estudiante y configurable. 14 días cubren el pedido semanal y dan visibilidad del siguiente |
| Corte y pedido semanal, cada lunes | Corte diario | Coincide con la frecuencia de decisión del negocio |
| Cobertura del pedido: días 2 a 8 tras el corte (supuesto) | Pedir para el día siguiente | Da un día de preparación y cubre una semana completa |
| Sin datos de inventario, el pedido es necesidad bruta | Inventar un inventario | Los datos no incluyen existencias ni quiebres; inventarlos restaría trazabilidad |
| Series sin ventas en 28 días o tiendas sin ventas en 7 días reciben pedido 0 con una marca | Pedir por el modelo | Evita pedir para series inactivas o tiendas cerradas, y deja explícita la razón |

## Disponibilidad temporal de los datos

Principio: toda predicción se construye solo con la información disponible cuando se emite.

| Decisión | Alternativas | Justificación |
|---|---|---|
| Almacén bitemporal: cada observación guarda fecha de negocio, fecha de entrega y fecha desde la que se conoce | Una tabla única actualizada | Permite responder qué se sabía en cualquier fecha y conservar la historia |
| Toda feature se construye con `as_of(corte)` | Filtrar por fecha en cada feature | Un único punto de acceso evita fugas por construcción |
| La disponibilidad sale de la fecha de entrega, nunca del reloj | Hora de ejecución o fecha del archivo | Hace determinista el backfill y reproducible cualquier ejecución |
| Fuentes separadas por frecuencia y retraso, en `config/fuentes.yaml` | Tratar todas igual | El enunciado pide distinta frecuencia y anticipación |
| Con una bandeja externa, la carga histórica sigue saliendo de los archivos de Kaggle | Exigir el histórico dentro de la bandeja | El enunciado parte de los archivos de Kaggle y de un periodo posterior no publicado |
| Petróleo: solo el último valor conocido; nunca precios futuros | Usar el archivo completo | `oil.csv` llega más allá del fin de las ventas |
| Feriados: anuales desde enero; traslados y puentes con 14 días; eventos imprevistos el mismo día (supuesto) | Conocerlos todos por adelantado | Un traslado o un terremoto no se conocen con un año de anticipación |
| Promociones: plan semanal publicado cada domingo (supuesto) | Usar `onpromotion` futuro sin restricción | Limita la información futura a lo que un plan podría conocer |
| Tienda nueva: se conoce desde su apertura | Conocerla desde `stores.csv` | Evita usar información de una tienda antes de que exista |

**Supuestos pendientes de contraste:** Kaggle no publica cuándo estuvo disponible cada dato. Las frecuencias, retrasos y anticipaciones de `config/fuentes.yaml` son del proyecto. El plan de promociones coincide con el valor real, lo que puede ser optimista.

## Datos tardíos y correcciones

| Decisión | Alternativas | Justificación |
|---|---|---|
| Un archivo tardío no existe hasta su entrega | Recalcular el pasado | Refleja lo que se sabía en cada fecha |
| Cada observación recibe una secuencia persistente, y gana la última | Sobrescribir; desempatar por hash | La secuencia es determinista y expresa el orden real |
| Solo es duplicado la reentrega de la versión vigente | Duplicado contra cualquier versión anterior | Una corrección puede volver a un contenido anterior |
| Un archivo descubierto tras una ejecución que cubría su entrega conserva su entrega original y se conoce desde su primera observación | Aceptar su entrega original | Lo ya consultado no debe cambiar |
| Las versiones se combinan por clave | Reemplazar el día completo | Permite recibir datos por partes. Consecuencia: una corrección no retira filas; ver `docs/deuda_tecnica.md` |
| Lo publicado es inmutable; una corrección crea una revisión | Sobrescribir | Conserva qué se recomendó y con qué información |
| Revisión automática solo antes de iniciar la cobertura | Revisar siempre | Después de iniciar la cobertura, el pedido ya se ejecutó |

## Validación y cuarentena

| Decisión | Alternativas | Justificación |
|---|---|---|
| Separar situaciones esperadas de datos inválidos | Fallar ante cualquier anomalía | El enunciado pide no fallar por situaciones del negocio |
| Archivo inválido: cuarentena completa, con motivo, y las demás entregas continúan | Aceptar las filas válidas; detener el flujo | Evita contaminar el resultado sin detener la operación |
| Datos faltantes, tardíos o parciales: advertencia | Rellenar con 0 | Un dato ausente no significa venta cero |
| Valores extremos: advertencia, no rechazo | Rechazar por rango | Existen ventas extremas reales en los datos |
| Completitud por series esperadas | Contar filas | Un conteo correcto puede ocultar tiendas sustituidas |
| Completitud según la frecuencia de cada fuente | Una regla común | Evita falsas alarmas en fines de semana y días sin operación |
| Claves con formato estricto | Normalizar en silencio | Una clave mal escrita no debe crear series nuevas |
| Publicación omitida si las ventas están muy atrasadas, con motivo | Publicar igual; fallar | Evita una recomendación poco fiable sin marcar un error de operación |

## Modelos

| Decisión | Alternativas | Justificación |
|---|---|---|
| Baseline: promedio de los últimos cuatro días equivalentes | Último valor | Simple, y captura el patrón semanal |
| Candidatos: LightGBM (objetivos logarítmico y Poisson) y HistGradientBoosting (Poisson) | Deep learning | Modelos de árboles entrenan en segundos con la memoria disponible. Deep learning aumentaría costo y complejidad sin justificación previa |
| Interfaz común y mismos cortes para todos | Evaluar cada modelo por separado | La comparación solo es válida en igualdad de condiciones |
| 8 cortes de validación, de 2016-08-29 a 2017-03-13, con calibración posterior al entrenamiento | Partición aleatoria | Respeta el tiempo. La bandeja no participa en entrenamiento, calibración ni selección |
| Features limitadas a datos desde 2015 | Toda la historia | Hay cambios de régimen en 2013-2014 y menor uso de memoria |
| Entrenar y reproducir dentro de la imagen | Usar el host | Las predicciones pueden diferir entre entornos; dentro de la imagen son idénticas entre corridas |
| Semilla e hilos fijos, modo determinista | Valores por defecto | Reproducibilidad |

### Incertidumbre

Un solo modelo puntual, con cuantiles desde residuos escalados fuera de muestra, por familia, volumen y horizonte, con respaldo por familia y global.

| Alternativa | Por qué no |
|---|---|
| Un modelo por cuantil | Más memoria, y cambiar costos exigiría reentrenar |

La escala del periodo incluye la demanda prevista. Los cuantiles se monitorean en el seguimiento, porque el modelo final se reentrena con todos los datos y conserva el calibrador previo.

### Criterio de reemplazo

El candidato reemplaza al vigente solo si cumple todas las condiciones de `config/modelo.yaml`, con los mismos cortes:

| Condición | Umbral |
|---|---|
| Costo de negocio | Al menos 3 % menor |
| WAPE | No peor en más de 1 % |
| Pinball loss | No peor |
| Consistencia | Menor costo en al menos 6 de 8 cortes |
| Cobertura P10-P90 | Entre 72 % y 88 % |
| Cobertura de Q* | A ±5 puntos del objetivo |

**Resultado:** el baseline sigue vigente, porque ningún candidato cumple todas las condiciones. El mejor, `lightgbm_poisson`, reduce el costo de negocio un 43,7 %, mejora WAPE y pinball y gana 6 de 8 cortes, pero su cobertura de Q* es 73,5 % para un objetivo de 80 %. `hgb_poisson` cumple las coberturas, pero gana 5 de 8 cortes. El detalle está en `docs/evidencia/modelos/comparacion.md`.

Los modelos de ML mejoran al baseline en las métricas técnicas y de negocio. El producto conserva el baseline porque el criterio exige además una incertidumbre calibrada para las recomendaciones, y los umbrales no se ajustan para facilitar un reemplazo.

## Pedido sugerido

| Decisión | Alternativas | Justificación |
|---|---|---|
| Cuantil crítico `Q* = Cu / (Cu + Co)` | Pronóstico puntual más margen fijo | Traduce directamente el balance entre faltante y merma |
| Cuantil de la demanda **acumulada** del periodo | Sumar cuantiles diarios | La suma de cuantiles no es el cuantil de la suma |
| Costos solo en `config/costos.yaml` | Parámetros en código | Cambiar los costos cambia la recomendación sin tocar código ni reentrenar |
| Costos por grupo de familias | Un costo único | Perecibles y productos de alta rotación tienen riesgos distintos |

Los costos son **supuestos académicos ilustrativos, no costos reales de Corporación Favorita**.

## Versionado y reproducción

| Decisión | Alternativas | Justificación |
|---|---|---|
| Git solo guarda código, configuración y referencias `.dvc` | Datos en Git | Requisito del enunciado |
| DVC con remoto exclusivamente local | Servicios en la nube | Decisión del proyecto: sin credenciales ni servicios externos |
| Remoto en `../dvc-storage/lab1`, fuera del repositorio y de los volúmenes de Docker | Volumen de Docker | Persiste al reconstruir el proyecto |
| `.tar` con SHA-256 en otro medio físico | Confiar en el remoto | El remoto comparte disco con el proyecto. Debe entregarse o respaldarse para que otro equipo recupere los datos |
| `verify = true` en el remoto | Valor por defecto | Evita restaurar un objeto corrupto sin error |
| Manifiesto con commit, hashes de datos, modelo y configuración, corte, horizonte y revisión | Registro libre | Vincula cada resultado con lo que lo produjo |
| Estado separado del manifiesto | Actualizar el manifiesto | El manifiesto es inmutable |
| `RESPALDADA` exige montaje real, centinela, `dvc push`, sincronía por JSON y hashes | Confiar en `dvc push` | Cada señal cubre un fallo que las demás no detectan |
| Rama `publicaciones` con commits creados sobre un índice temporal | Commits en `main` | `main` está protegida y el índice de trabajo no se altera |
| Un commit de publicación se detiene si contiene caché, datos o modelos | Confiar en `.gitignore` | Los objetos de la caché no tienen extensión y un filtro por nombre no los detecta |
| Publicaciones y etiquetas `pub/*` con solo referencias `.dvc` | Incluir datos en la etiqueta | Git no guarda datos; un clon recupera todo del remoto DVC |

**Reproducir** recalcula una publicación con su modelo y lo conocido en su fecha, y debe dar hashes idénticos. **Reprocesar** usa datos corregidos y crea una revisión nueva.

## Orquestación

| Decisión | Alternativas | Justificación |
|---|---|---|
| Airflow 3 con Docker Compose y LocalExecutor | CeleryExecutor | Suficiente para un equipo, con menos memoria |
| Orquestador `operacion_diaria` | Sensores entre DAGs | Garantiza el orden y permite un solo backfill |
| `make up` ejecuta el simulador antes de crear los servicios | Arranque simultáneo | Quien monta la bandeja debe verla ya instalada |
| Lógica en `src/`; los DAGs solo invocan funciones | Lógica en los DAGs | Se puede probar sin Airflow |
| Tareas pesadas en un pool de un cupo | Paralelismo | Memoria limitada y bloqueos de DVC |
| Tarea final `cierre` | Confiar en el estado de la corrida | Una corrida no debe quedar verde con un respaldo fallido |
| Reentrenamiento cada 4 semanas del tipo de modelo vigente | Reentrenar cada corte | Equilibra frescura y costo. Cambiar de tipo de modelo requiere `make evaluate` y su criterio |

## Repositorio y seguridad

| Decisión | Alternativas | Justificación |
|---|---|---|
| Repositorio público con `main` protegida | Privado | Protección de rama y acceso docente, sin datos ni credenciales |
| Enunciado y especificación fuera de Git | Publicarlos | Decisión del estudiante |
| Secretos generados en `.env`, fuera de Git | Valores por defecto | Repositorio público |
| Airflow solo en `127.0.0.1` | Todas las interfaces | Reduce la exposición |
| Versiones fijadas según las constraints de Airflow | Rangos abiertos | Reproducibilidad |

## Limitaciones conocidas

- Sin inventario ni quiebres, las ventas no equivalen a demanda.
- Los costos y las fechas de disponibilidad son supuestos.
- El plan de promociones puede sobreestimar lo que se conocería en la realidad.
- La recuperación cubre interrupciones del proceso; un corte de energía podría exigir restaurar con DVC.
- Otras limitaciones están en `docs/deuda_tecnica.md`.
