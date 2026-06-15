#!/usr/bin/env python3
"""Convierte sesiones de Claude Code (.jsonl) a Markdown legible.
Título: usa ai-title si existe; si no, genera uno del primer mensaje del usuario.
Fecha: del primer timestamp. Proyecto: del nombre de carpeta.
Uso: convert_claude.py <carpeta_conversaciones> <carpeta_salida>
"""
import json, os, re, sys, glob

def fmt_tool_use(c):
    name = c.get("name", "herramienta")
    inp = c.get("input", {}) or {}
    if name in ("Edit", "Write", "Read", "NotebookEdit"):
        return f"[herramienta: {name} → {inp.get('file_path') or inp.get('path','')}]"
    if name == "Bash":
        return f"[herramienta: Bash]\n```bash\n{(inp.get('command') or '').strip()}\n```"
    if name in ("Grep", "Glob"):
        return f"[herramienta: {name} → {inp.get('pattern','')}]"
    if name in ("WebSearch", "WebFetch"):
        return f"[herramienta: {name} → {inp.get('query') or inp.get('url','')}]"
    blob = json.dumps(inp, ensure_ascii=False)
    if len(blob) > 300:
        blob = blob[:300] + " …"
    return f"[herramienta: {name} {blob}]"

def fmt_tool_result(c):
    content = c.get("content", "")
    if isinstance(content, list):
        content = "\n".join(x.get("text", "") for x in content if isinstance(x, dict))
    content = str(content).strip()
    if len(content) > 500:
        content = content[:500] + " …(recortado)"
    return f"[resultado]\n```\n{content}\n```" if content else ""

def render(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for c in content:
            if not isinstance(c, dict):
                if isinstance(c, str):
                    out.append(c)
                continue
            t = c.get("type")
            if t == "text":
                out.append(c.get("text", ""))
            elif t == "tool_use":
                out.append(fmt_tool_use(c))
            elif t == "tool_result":
                r = fmt_tool_result(c)
                if r:
                    out.append(r)
            elif "text" in c:
                out.append(c["text"])
        return "\n\n".join(p for p in out if p and str(p).strip())
    return ""

def first_user_text(content):
    """Para generar título desde el primer mensaje del usuario."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict) and c.get("type") in ("text", None) and c.get("text"):
                return c["text"]
            if isinstance(c, str):
                return c
    return ""

def clean_title(s):
    """Limpia un texto para usarlo como título: descarta comandos/ruido, recorta en palabra."""
    if not s:
        return None
    s = s.strip()
    # descartar prompts que son solo comandos internos
    if s.startswith("<command-name>") or s.startswith("<") and ">" in s[:30] and len(s) < 40:
        return None
    s = s.replace("\n", " ").strip()
    if not s:
        return None
    if len(s) > 70:
        cut = s[:70].rsplit(" ", 1)[0]
        s = (cut or s[:70]) + "…"
    return s

def parse_session(path, history=None, fuente="claude-code"):
    title = None
    first_user = None
    first_ts = None
    cwd = None
    sid = None
    blocks = []

    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = d.get("type")
        if first_ts is None and d.get("timestamp"):
            first_ts = d["timestamp"]
        if cwd is None and d.get("cwd"):
            cwd = d["cwd"]
        if sid is None and d.get("sessionId"):
            sid = d["sessionId"]

        if t == "ai-title":
            title = d.get("aiTitle")
        elif t in ("user", "assistant"):
            msg = d.get("message", {})
            role = msg.get("role", t)
            content = msg.get("content", "")
            if role == "user" and first_user is None:
                first_user = first_user_text(content)
            txt = render(content)
            if txt.strip():
                label = "Tú" if role == "user" else "Claude"
                blocks.append(f"### {label}\n\n{txt}\n")

    # prioridad de título: ai-title > history.jsonl (primer prompt real) > primer mensaje > uuid
    if not title and history and sid and sid in history:
        title = clean_title(history[sid])
    if not title and first_user:
        title = clean_title(first_user)
    if not title:
        title = "sesion-" + os.path.splitext(os.path.basename(path))[0][:20]

    project = os.path.basename(cwd.rstrip("/")) if cwd else ""
    return {
        "title": title,
        "date": (first_ts or "")[:10],
        "datetime": first_ts or "",
        "project": project,
        "fuente": fuente,
        "blocks": blocks,
    }

def safe_filename(s):
    s = re.sub(r"[^\w\s-]", "", s).strip().replace(" ", "_")
    return s[:80] or "sesion"

def project_label(folder):
    # El path viene como "-Users-<user>-<...>-<nombreProyecto>", así que el
    # último segmento es el nombre del proyecto (agnóstico al usuario/estructura).
    parts = [p for p in folder.split("-") if p]
    label = parts[-1] if parts else folder
    return normalize_project(label)

def normalize_project(label):
    """Quita sufijos que el Finder agrega al recuperar de snapshots:
    ' (del respaldo)', ' (del respaldo 2)', ' 2', ' copia', etc.
    Así variantes de un mismo proyecto se unifican."""
    s = label
    s = re.sub(r"\s*\(del respaldo[^)]*\)", "", s)
    s = re.sub(r"\s*\(copia[^)]*\)", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+\d+$", "", s)   # ' 2' al final
    return s.strip() or label

def load_history(path):
    """Mapea sessionId -> primer prompt del usuario desde history.jsonl."""
    hist = {}
    if not path or not os.path.exists(path):
        return hist
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        sid = d.get("sessionId")
        disp = d.get("display")
        if sid and disp and sid not in hist:
            hist[sid] = disp
    return hist

def main():
    # uso: convert_claude.py <conversaciones> <salida> [fuente] [history.jsonl]
    src, out_dir = sys.argv[1], sys.argv[2]
    fuente = sys.argv[3] if len(sys.argv) > 3 else "claude-code"
    hist_path = sys.argv[4] if len(sys.argv) > 4 else os.path.expanduser("~/.claude/history.jsonl")
    history = load_history(hist_path)
    counts = {"ok": 0, "empty": 0, "dups": 0}

    # 1) Recolectar todos los .jsonl agrupando por (proyecto normalizado, uuid de sesión).
    #    El uuid es el nombre del archivo sin extensión. Si la misma sesión aparece en
    #    varias carpetas (ej. "mi-proyecto" y "mi-proyecto (del respaldo)"),
    #    nos quedamos con el archivo más grande (el más completo).
    best = {}  # (plabel, uuid) -> (size, filepath)
    for proj_dir in sorted(glob.glob(os.path.join(src, "*"))):
        if not os.path.isdir(proj_dir):
            continue
        plabel = project_label(os.path.basename(proj_dir))
        for f in glob.glob(os.path.join(proj_dir, "*.jsonl")):
            uuid = os.path.splitext(os.path.basename(f))[0]
            try:
                size = os.path.getsize(f)
            except OSError:
                size = 0
            k = (plabel, uuid)
            if k not in best or size > best[k][0]:
                if k in best:
                    counts["dups"] += 1
                best[k] = (size, f)
            else:
                counts["dups"] += 1

    # 2) Convertir un archivo por sesión única.
    for (plabel, uuid), (size, f) in best.items():
        s = parse_session(f, history=history, fuente=fuente)
        if not s["blocks"]:
            counts["empty"] += 1
            continue
        proj = plabel or s["project"] or "sin-proyecto"
        pdir = os.path.join(out_dir, proj)
        os.makedirs(pdir, exist_ok=True)
        base = safe_filename(s["title"])
        prefix = s["date"] or "0000-00-00"
        fname = f"{prefix}__{base}__{uuid}.md"   # uuid completo = sin colisiones
        with open(os.path.join(pdir, fname), "w") as o:
            o.write(f"# {s['title']}\n\n")
            o.write(f"<!-- fecha: {s['datetime']} | id: {uuid} | proyecto: {proj} | fuente: {fuente} -->\n\n")
            o.write("\n".join(s["blocks"]))
        counts["ok"] += 1

    print(f"Convertidas: {counts['ok']}")
    print(f"Vacías: {counts['empty']}")
    if counts["dups"]:
        print(f"Duplicados omitidos (misma sesión en varias carpetas): {counts['dups']}")
    if history:
        print(f"(history.jsonl aportó {len(history)} prompts para títulos)")

    # sello de backup: fecha de esta corrida por fuente
    try:
        import datetime
        info_path = os.path.join(out_dir, "_backup-info.json")
        info = {}
        if os.path.exists(info_path):
            try: info = json.load(open(info_path))
            except Exception: info = {}
        info[fuente] = {"generado": datetime.datetime.now().astimezone().isoformat(), "conversaciones": counts["ok"]}
        os.makedirs(out_dir, exist_ok=True)
        json.dump(info, open(info_path, "w"), ensure_ascii=False, indent=2)
    except Exception:
        pass

if __name__ == "__main__":
    main()
