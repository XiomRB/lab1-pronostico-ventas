# Deuda técnica de la ingesta

Limitaciones conocidas, **no resueltas**. Ninguna afecta a los resultados con los datos actuales.

## D8: una corrección no puede retirar una fila

| Aspecto | Detalle |
|---|---|
| Descripción | Las versiones se combinan por clave. Si una corrección omite una fila, la fila anterior sigue vigente |
| Impacto | Una fila errónea entregada por error no se puede eliminar; solo se puede corregir su valor |
| Riesgo para la evaluación | Medio: una corrección que elimine registros dejaría esos registros en los pronósticos |
| Motivo del aplazamiento | Combinar por clave es lo que permite recibir archivos por partes. Cambiarlo exige distinguir entre entregas parciales y reemplazos |
| Solución futura | Marcar en el contrato las entregas de reemplazo completo, o admitir registros de baja explícitos |

## D9: regenerar la bandeja sobre un almacén existente

| Aspecto | Detalle |
|---|---|
| Descripción | Si cambia la semilla o el periodo y se regenera la bandeja, la ingesta añade esas entregas al almacén previo |
| Impacto | El almacén mezcla observaciones de dos simulaciones distintas |
| Riesgo para la evaluación | Bajo: una instalación limpia parte de un almacén vacío. Medio si se reutiliza un almacén previo |
| Motivo del aplazamiento | Es una situación de operación manual, que se evita partiendo de un almacén vacío |
| Solución futura | Guardar en el almacén la huella de la simulación y detener la ingesta si no coincide |

## D10: referencia histórica guardada

| Aspecto | Detalle |
|---|---|
| Descripción | `referencia_historica.json` se calcula una vez. Cambiar `cuantil_extremo` o el histórico no la actualiza |
| Impacto | Los umbrales de advertencia pueden quedar desactualizados |
| Riesgo para la evaluación | Bajo: solo afecta a advertencias, no a qué datos se aceptan |
| Motivo del aplazamiento | No altera resultados y se soluciona borrando ese archivo generado |
| Solución futura | Guardar la huella del histórico y de la configuración, y recalcular si cambian |

## D11: partición perdida del almacén

| Aspecto | Detalle |
|---|---|
| Descripción | Si se borra una partición, el registro la sigue dando por procesada y la reingesta no la recupera |
| Impacto | `as_of` omitiría esas filas sin aviso, salvo por los avisos de completitud |
| Riesgo para la evaluación | Bajo: exige borrar manualmente archivos internos, y DVC puede restaurarlos |
| Motivo del aplazamiento | No ocurre en la operación normal y existe recuperación con DVC |
| Solución futura | Comprobar en cada ejecución que toda entrada aceptada conserva su partición |

## D12: motivo compartido en cuarentena

| Aspecto | Detalle |
|---|---|
| Descripción | Dos archivos inválidos con el mismo contenido comparten carpeta y `motivo.json` |
| Impacto | El motivo conserva solo el último nombre; ambos archivos y sus entradas de registro se conservan |
| Riesgo para la evaluación | Bajo: la trazabilidad completa está en `data/almacen/registro/` |
| Motivo del aplazamiento | No pierde información relevante |
| Solución futura | Guardar un motivo por archivo, o usar el nombre además del hash en la carpeta |
