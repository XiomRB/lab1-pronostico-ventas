#!/usr/bin/env bash
# Verifica un respaldo y lo restaura. No sobrescribe un remoto existente.
set -euo pipefail
archivo=${1:?Indica el archivo .tar}
destino=${2:-../dvc-storage}
(cd "$(dirname "$archivo")" && sha256sum -c "$(basename "$archivo").sha256")
if [ -e "$destino/lab1" ]; then
  echo "Ya existe $destino/lab1; muévelo antes de restaurar" >&2
  exit 1
fi
mkdir -p "$destino"
tar -C "$destino" -xf "$archivo"
echo "Remoto restaurado en $destino/lab1"
