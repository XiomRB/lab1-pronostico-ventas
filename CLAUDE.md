# lab1-pronostico-ventas

Producto que convierte ventas diarias en un pronóstico con incertidumbre y un pedido sugerido semanal por tienda y familia.

La especificación es `docs/diseno_tecnico_lab1.md` y el enunciado es `docs/instrucciones_lab1.md`. Ambos son locales: Git los ignora y nunca se publican. No propongas alternativas ya descartadas ahí.

## Reglas del proyecto

- Cada fase requiere autorización expresa del estudiante antes de ejecutarse.
- Trabaja en ramas y Pull Requests. `main` está protegida.
- Toda predicción usa solo información disponible en su fecha: `fecha_entrega ≤ corte`, nunca la hora del sistema.
- La bandeja es de solo lectura para el flujo.
- La lógica de negocio vive en `src/pronostico_ventas/` con pruebas. Los DAGs solo orquestan.
- Las tareas son idempotentes. No uses `now()` en lógica de negocio.
- Los costos viven solo en `config/costos.yaml`. Son supuestos académicos.
- Las publicaciones son inmutables. Una corrección genera una nueva revisión.
- No asumas que LightGBM es mejor: decide el criterio cuantitativo de `config/modelo.yaml`.

## Datos, modelos y seguridad

- Git nunca guarda datos ni modelos. DVC es el único mecanismo para versionarlos.
- DVC es exclusivamente local: remoto `../dvc-storage/lab1`, con `verify = true`. No agregues remotos externos.
- El remoto local no sustituye al respaldo `.tar` en otro medio físico.
- `.env` nunca entra a Git. Los secretos se generan localmente.
- No incluyas credenciales, rutas personales, correos personales ni datos reales en archivos versionados.
- Una publicación solo es `RESPALDADA` si cumple las cinco condiciones de la especificación.
- No detengas ni modifiques otros proyectos de Docker sin autorización.
- `rm -rf data` borra también las referencias `.dvc`: no lo uses.

## Entorno

- Python 3.12 en `.venv`. Instala con `make instalar` y prueba con `make test`.
- Las versiones siguen las constraints de Airflow 3.3.2. Si cambias una, documéntalo en `DECISIONES.md`.
- Airflow solo es accesible desde localhost.
- Las pruebas no dependen de los datos de Kaggle: usan datos sintéticos.
