#!/usr/bin/env bash
# Doble clic para actualizar el respaldo de conversaciones.
# Este wrapper corre actualizar-respaldo.sh que está en la misma carpeta.
cd "$(dirname "$0")" || exit 1
./actualizar-respaldo.sh
echo ""
echo "──────────────────────────────────────────"
read -r -p "Listo. Apretá Enter para cerrar esta ventana."
