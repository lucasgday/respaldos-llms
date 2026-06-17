#!/usr/bin/env bash
# install-auto.command
# Installs (or reinstalls) the launchd task that runs the backup every day.
# Double-click to install at the default time (12:00). Or run from the terminal
# with a time to pick when it runs:
#   ./install-auto.command 22       → every day at 22:00
#   ./install-auto.command 7:30     → every day at 07:30
# The base is the folder where this file lives.

cd "$(dirname "$0")" || exit 1
BASE="$(pwd)"
SCRIPT="$BASE/update-backup.sh"
LABEL="com.agentlog.backup"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# ---------- pick the time (default 12:00) ----------
HOUR=12; MIN=0
case "${1:-}" in
  -h|--help)
    echo "Usage: install-auto.command [HH | HH:MM]   (default 12:00)"
    echo "Examples: install-auto.command 22   |   install-auto.command 7:30"
    exit 0;;
  "") ;;  # no argument → default 12:00
  *)
    if [[ "$1" =~ ^([0-9]{1,2})(:([0-9]{1,2}))?$ ]]; then
      HOUR=$((10#${BASH_REMATCH[1]})); MIN=$((10#${BASH_REMATCH[3]:-0}))
    else
      echo "Invalid time: '$1'. Use HH or HH:MM (24h), e.g. 22 or 7:30."
      read -r -p "Press Enter to close."; exit 1
    fi
    if (( HOUR > 23 || MIN > 59 )); then
      echo "Out-of-range time: '$1'. Hour 0-23, minute 0-59."
      read -r -p "Press Enter to close."; exit 1
    fi;;
esac
HHMM=$(printf "%02d:%02d" "$HOUR" "$MIN")

echo "== Install daily automatic backup ($HHMM) =="
echo "Base folder: $BASE"

if [ ! -f "$SCRIPT" ]; then
  echo "ERROR: can't find update-backup.sh in this folder."
  read -r -p "Press Enter to close."; exit 1
fi
chmod +x "$SCRIPT"

mkdir -p "$HOME/Library/LaunchAgents"

# Write the .plist. RunAtLoad=false so it doesn't run on install; StartCalendarInterval = chosen time.
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
        <integer>$HOUR</integer>
        <key>Minute</key>
        <integer>$MIN</integer>
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

# reload: unload if already present, then load again
launchctl unload "$PLIST" 2>/dev/null
if launchctl load "$PLIST" 2>/dev/null; then
  echo "✓ Installed. The backup will run every day at $HHMM (or when the Mac wakes up if it was asleep)."
  echo "  To see it working: open the viewer and check the run-history panel, or look at $BASE/.sync-state/log.json"
else
  echo "There was a problem loading the task. macOS may ask for Full Disk Access."
  echo "System Settings → Privacy & Security → Full Disk Access → add 'bash' or Terminal."
fi
echo ""
read -r -p "Done. Press Enter to close."
