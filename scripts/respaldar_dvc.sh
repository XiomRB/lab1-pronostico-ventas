#!/usr/bin/env bash
# Crea un .tar del remoto DVC con su SHA-256. DESTINO debe estar en otro medio físico.
set -euo pipefail
destino=${1:?Indica la carpeta de destino}
remoto=${2:-../dvc-storage/lab1}
archivo="dvc-storage-lab1-$(date +%Y%m%d-%H%M%S).tar"
mkdir -p "$destino"
tar -C "$(dirname "$remoto")" -cf "$destino/$archivo" "$(basename "$remoto")"
(cd "$destino" && sha256sum "$archivo" > "$archivo.sha256")
echo "$destino/$archivo"
