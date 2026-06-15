#!/usr/bin/env bash
# instalar-automatico.command
# Instala (o reinstala) la tarea de launchd que corre el respaldo todos los días al mediodía.
# Doble clic para instalar. La base es la carpeta donde vive este archivo.

cd "$(dirname "$0")" || exit 1
BASE="$(pwd)"
SCRIPT="$BASE/actualizar-respaldo.sh"
LABEL="com.respaldos-llms.backup"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "== Instalar respaldo automático diario (12:00) =="
echo "Carpeta base: $BASE"

if [ ! -f "$SCRIPT" ]; then
  echo "ERROR: no encuentro actualizar-respaldo.sh en esta carpeta."
  read -r -p "Enter para cerrar."; exit 1
fi
chmod +x "$SCRIPT"

mkdir -p "$HOME/Library/LaunchAgents"

# Escribir el .plist. RunAtLoad=false para no correr al instalar; StartCalendarInterval = 12:00.
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SCRIPT</string>
        <string>$BASE</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>12</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$BASE/.sync-state/launchd-out.log</string>
    <key>StandardErrorPath</key>
    <string>$BASE/.sync-state/launchd-err.log</string>
</dict>
</plist>
PLISTEOF

mkdir -p "$BASE/.sync-state"

# recargar: descargar si ya estaba, y cargar de nuevo
launchctl unload "$PLIST" 2>/dev/null
if launchctl load "$PLIST" 2>/dev/null; then
  echo "✓ Instalado. El respaldo correrá todos los días a las 12:00 (o al despertar la Mac si estaba dormida)."
  echo "  Para verlo andar: abrí el visor y mirá el panel de últimas corridas, o revisá $BASE/.sync-state/log.json"
else
  echo "Hubo un problema al cargar la tarea. Puede que macOS pida permiso de Acceso Total al Disco."
  echo "Ajustes del Sistema → Privacidad y Seguridad → Acceso total al disco → agregá 'bash' o la Terminal."
fi
echo ""
read -r -p "Listo. Enter para cerrar."
