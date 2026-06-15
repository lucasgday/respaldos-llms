#!/usr/bin/env bash
# desinstalar-automatico.command
# Quita la tarea de launchd del respaldo automático. Doble clic para desinstalar.

LABEL="com.respaldos-llms.backup"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "== Desinstalar respaldo automático =="
if [ -f "$PLIST" ]; then
  launchctl unload "$PLIST" 2>/dev/null
  rm -f "$PLIST"
  echo "✓ Desinstalado. El respaldo ya no corre solo."
  echo "  (Seguís pudiendo correrlo a mano con actualizar-respaldo.command cuando quieras.)"
else
  echo "No estaba instalado (no encontré $PLIST)."
fi
echo ""
read -r -p "Listo. Enter para cerrar."
