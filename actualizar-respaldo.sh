#!/usr/bin/env bash
# actualizar-respaldo.sh
# Respaldo incremental y acumulativo de conversaciones de LLMs (Claude Code, Codex, Cowork).
# - Enfoque A: la base es la carpeta donde vive este script (se puede mover toda la carpeta).
# - Override opcional: pasar una ruta como primer argumento.
# - Incremental: procesa solo .jsonl nuevos o que cambiaron de tamaño desde la última corrida.
# - Acumulativo: nunca borra markdowns ya generados, aunque el origen los haya borrado (cleanup).
# - Sync de archivado (Codex): si una sesión pasó a archived_sessions, actualiza su .md a archivada:true.
# - Extensible: cada fuente es un bloque que se saltea si su origen no existe.

set -uo pipefail

# ---------- ubicación base ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="${1:-$SCRIPT_DIR}"           # override opcional por argumento
cd "$BASE" || { echo "No pude entrar a $BASE"; exit 1; }

STATE="$BASE/.sync-state"          # índice de tamaños procesados (incremental)
mkdir -p "$STATE"
TMP="$BASE/.sync-tmp"
PY_CLAUDE="$BASE/convert_claude.py"
PY_CODEX="$BASE/convert_codex.py"

HOME_CLAUDE="$HOME/.claude"
HOME_CODEX="$HOME/.codex"
COWORK_DIR="$HOME/Library/Application Support/Claude/local-agent-mode-sessions"

echo "== Respaldo LLMs =="
echo "Base: $BASE"
echo ""

# Función: ¿este .jsonl es nuevo o cambió de tamaño desde la última vez?
# Guarda el tamaño en $STATE/<hash>.size  (hash = ruta codificada)
need_process() {
  local f="$1" key sz prev
  key=$(echo "$f" | shasum | cut -d' ' -f1)
  sz=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null)
  prev=$(cat "$STATE/$key.size" 2>/dev/null || echo "")
  if [ "$sz" != "$prev" ]; then
    echo "$sz" > "$STATE/$key.size"
    return 0   # procesar
  fi
  return 1     # sin cambios, saltar
}

# ---------------------------------------------------------------------------
# FUENTE 1: Claude Code  (~/.claude/projects/*/*.jsonl)
# ---------------------------------------------------------------------------
if [ -d "$HOME_CLAUDE/projects" ]; then
  echo "-- Claude Code --"
  SRC="$TMP/claude/conversaciones"
  rm -rf "$TMP/claude"; mkdir -p "$SRC"
  nuevos=0
  while IFS= read -r -d '' f; do
    [[ "$f" == *"/subagents/"* ]] && continue
    [[ "$(basename "$f")" == agent-* ]] && continue
    if need_process "$f"; then
      proj=$(basename "$(dirname "$f")")
      mkdir -p "$SRC/$proj"
      cp "$f" "$SRC/$proj/$(basename "$f")"
      nuevos=$((nuevos+1))
    fi
  done < <(find "$HOME_CLAUDE/projects" -name "*.jsonl" -print0 2>/dev/null)
  if [ "$nuevos" -gt 0 ]; then
    echo "  $nuevos sesiones nuevas/cambiadas → convirtiendo"
    python3 "$PY_CLAUDE" "$SRC" "$BASE/markdown-claude" claude-code "$HOME_CLAUDE/history.jsonl"
  else
    echo "  sin cambios"
  fi
else
  echo "-- Claude Code -- (no encontrado, salteado)"
fi
echo ""

# ---------------------------------------------------------------------------
# FUENTE 2: Codex  (~/.codex/sessions y ~/.codex/archived_sessions)
# ---------------------------------------------------------------------------
if [ -d "$HOME_CODEX/sessions" ] || [ -d "$HOME_CODEX/archived_sessions" ]; then
  echo "-- Codex --"
  IDX="$HOME_CODEX/session_index.jsonl"

  # Activas
  if [ -d "$HOME_CODEX/sessions" ]; then
    SRC="$TMP/codex-act"; rm -rf "$SRC"; mkdir -p "$SRC/all"
    nuevos=0
    while IFS= read -r -d '' f; do
      if need_process "$f"; then cp "$f" "$SRC/all/$(basename "$f")"; nuevos=$((nuevos+1)); fi
    done < <(find "$HOME_CODEX/sessions" -name "*.jsonl" -print0 2>/dev/null)
    if [ "$nuevos" -gt 0 ]; then
      echo "  $nuevos activas nuevas/cambiadas → convirtiendo"
      python3 "$PY_CODEX" "$SRC" "$IDX" "$BASE/markdown-codex"
    else
      echo "  activas: sin cambios"
    fi
  fi

  # Archivadas: conversión INCREMENTAL (solo nuevas/cambiadas) + sync de flag barato.
  if [ -d "$HOME_CODEX/archived_sessions" ]; then
    SRC="$TMP/codex-arch"; rm -rf "$SRC"; mkdir -p "$SRC/all"
    nuevos=0
    while IFS= read -r -d '' f; do
      if need_process "$f"; then cp "$f" "$SRC/all/$(basename "$f")"; nuevos=$((nuevos+1)); fi
    done < <(find "$HOME_CODEX/archived_sessions" -name "*.jsonl" -print0 2>/dev/null)
    if [ "$nuevos" -gt 0 ]; then
      echo "  $nuevos archivadas nuevas/cambiadas → convirtiendo"
      python3 "$PY_CODEX" "$SRC" "$IDX" "$BASE/markdown-codex" archived
    else
      echo "  archivadas: sin cambios"
    fi
    # Sync de flag (barato): detecta sesiones que se MOVIERON a archivadas y cuyo .md sigue diciendo
    # archivada:false. Las marca true sin reconvertir, y elimina duplicados activa/archivada.
    python3 - "$BASE/markdown-codex" "$HOME_CODEX/archived_sessions" <<'PYEOF'
import sys, glob, os, re, json
mddir, archdir = sys.argv[1], sys.argv[2]
# ids actualmente archivados
arch_ids=set()
for f in glob.glob(os.path.join(archdir,'**','*.jsonl'), recursive=True):
    for l in open(f):
        l=l.strip()
        if not l: continue
        try: o=json.loads(l)
        except: continue
        if o.get('type')=='session_meta':
            sid=o.get('payload',{}).get('id')
            if sid: arch_ids.add(sid)
            break
# indexar markdowns por id, con su estado de archivado
by_id={}
for f in glob.glob(os.path.join(mddir,'**','*.md'), recursive=True):
    txt=open(f).read()
    m=re.search(r'id:\s*([0-9a-f-]{36})', txt)
    if not m: continue
    by_id.setdefault(m.group(1),[]).append([f, 'archivada: true' in txt, txt])
marcados=0; borrados=0
for sid in arch_ids:
    if sid not in by_id: continue
    lst=by_id[sid]
    tiene_true=any(a for _,a,_ in lst)
    if not tiene_true:
        # ningún .md de este id está marcado archivada:true → marcar el (único) existente
        for item in lst:
            f,a,txt=item
            nuevo=re.sub(r'archivada:\s*false','archivada: true',txt,count=1)
            if nuevo!=txt:
                open(f,'w').write(nuevo); marcados+=1; item[1]=True
    # eliminar duplicados activa:false si ya hay uno true
    if any(a for _,a,_ in by_id[sid]):
        for f,a,_ in by_id[sid]:
            if not a and os.path.exists(f):
                os.remove(f); borrados+=1
msg=[]
if marcados: msg.append(f"{marcados} marcadas archivada")
if borrados: msg.append(f"{borrados} duplicados activos eliminados")
if msg: print("  sync flag: "+", ".join(msg))
PYEOF
  fi
else
  echo "-- Codex -- (no encontrado, salteado)"
fi
echo ""

# ---------------------------------------------------------------------------
# FUENTE 3: Cowork  (estructura anidada; conversaciones reales bajo .claude/projects)
# ---------------------------------------------------------------------------
if [ -d "$COWORK_DIR" ]; then
  echo "-- Cowork --"
  SRC="$TMP/cowork/cowork"; rm -rf "$TMP/cowork"; mkdir -p "$SRC"
  nuevos=0
  while IFS= read -r -d '' f; do
    if need_process "$f"; then cp "$f" "$SRC/$(basename "$f")"; nuevos=$((nuevos+1)); fi
  done < <(find "$COWORK_DIR" -path "*/.claude/projects/*.jsonl" ! -name "audit.jsonl" ! -path "*/subagents/*" -print0 2>/dev/null)
  if [ "$nuevos" -gt 0 ]; then
    echo "  $nuevos sesiones nuevas/cambiadas → convirtiendo"
    python3 "$PY_CLAUDE" "$TMP/cowork" "$BASE/markdown-cowork" cowork "$HOME_CLAUDE/history.jsonl"
  else
    echo "  sin cambios"
  fi
else
  echo "-- Cowork -- (no encontrado, salteado)"
fi
echo ""

# ---------------------------------------------------------------------------
# FUENTE 4: OpenCode  (~/.local/share/opencode/opencode.db, SQLite)
# Se reconvierte completo cuando la base cambió de tamaño (incremental a nivel base).
# ---------------------------------------------------------------------------
OPENCODE_DB="$HOME/.local/share/opencode/opencode.db"
PY_OPENCODE="$BASE/convert_opencode.py"
if [ -f "$OPENCODE_DB" ] && [ -f "$PY_OPENCODE" ]; then
  echo "-- OpenCode --"
  if need_process "$OPENCODE_DB"; then
    echo "  base cambió → convirtiendo"
    python3 "$PY_OPENCODE" "$OPENCODE_DB" "$BASE/markdown-opencode"
  else
    echo "  sin cambios"
  fi
elif [ ! -f "$PY_OPENCODE" ]; then
  echo "-- OpenCode -- (convert_opencode.py no encontrado, salteado)"
else
  echo "-- OpenCode -- (no encontrado, salteado)"
fi
echo ""

# ---------------------------------------------------------------------------
# FUENTE 5: Cursor  (globalStorage/state.vscdb, SQLite con composers + bubbles)
# El global tiene las conversaciones; se reconvierte si la base cambió de tamaño.
# ---------------------------------------------------------------------------
CURSOR_DB="$HOME/Library/Application Support/Cursor/User/globalStorage/state.vscdb"
PY_CURSOR="$BASE/convert_cursor.py"
if [ -f "$CURSOR_DB" ] && [ -f "$PY_CURSOR" ]; then
  echo "-- Cursor --"
  if need_process "$CURSOR_DB"; then
    echo "  base cambió → convirtiendo"
    python3 "$PY_CURSOR" "$CURSOR_DB" "$BASE/markdown-cursor"
  else
    echo "  sin cambios"
  fi
elif [ ! -f "$PY_CURSOR" ]; then
  echo "-- Cursor -- (convert_cursor.py no encontrado, salteado)"
else
  echo "-- Cursor -- (no encontrado, salteado)"
fi
echo ""

# limpiar temporales
rm -rf "$TMP"

echo "== Respaldo actualizado =="
echo "Markdowns:"
# contar por fuente y total, y registrar en el log
TOTAL=0
declare -a RESUMEN
for d in markdown-claude markdown-codex markdown-cowork markdown-opencode markdown-cursor; do
  if [ -d "$BASE/$d" ]; then
    n=$(find "$BASE/$d" -name '*.md' | wc -l | tr -d ' ')
    echo "  $d: $n"
    TOTAL=$((TOTAL + n))
    RESUMEN+=("\"${d#markdown-}\": $n")
  fi
done
echo "  TOTAL: $TOTAL"

# escribir registro de la corrida en log.json (historial de corridas, acumulativo)
LOG="$BASE/.sync-state/log.json"
mkdir -p "$BASE/.sync-state"
FECHA=$(date +"%Y-%m-%dT%H:%M:%S%z")
ENTRADA=$(printf '{"fecha":"%s","total":%d,%s}' "$FECHA" "$TOTAL" "$(IFS=,; echo "${RESUMEN[*]}")")
# anteponer la entrada nueva al historial (mantener últimas 50)
python3 - "$LOG" "$ENTRADA" <<'PYEOF'
import sys, json, os
log_path, entrada = sys.argv[1], sys.argv[2]
hist = []
if os.path.exists(log_path):
    try: hist = json.load(open(log_path))
    except Exception: hist = []
try: e = json.loads(entrada)
except Exception: e = {"fecha": "?", "total": 0}
hist.insert(0, e)
hist = hist[:50]
json.dump(hist, open(log_path, "w"), ensure_ascii=False, indent=2)
PYEOF

# notificación de macOS (solo si osascript existe, o sea en Mac)
if command -v osascript >/dev/null 2>&1; then
  osascript -e "display notification \"Total: $TOTAL conversaciones respaldadas\" with title \"Respaldo LLMs\" sound name \"\"" >/dev/null 2>&1 || true
fi

echo ""
echo "Abrí viewer.html y apuntá a: $BASE"
