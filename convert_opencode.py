#!/usr/bin/env python3
"""Convierte sesiones de OpenCode (opencode.db SQLite) a Markdown legible.
Estructura: session (título, directorio) -> message (role) -> part (texto/tool).
Uso: convert_opencode.py <ruta_opencode.db> <carpeta_salida>
"""
import sqlite3, json, os, re, sys, datetime

def safe_filename(s):
    s = re.sub(r"[^\w\s-]", "", s or "").strip().replace(" ", "_")
    return s[:80] or "sesion"

def project_label(directory):
    if not directory:
        return "sin-proyecto"
    return os.path.basename(directory.rstrip("/")) or "sin-proyecto"

def ms_to_iso(ms):
    if not ms:
        return ""
    try:
        return datetime.datetime.fromtimestamp(int(ms)/1000, datetime.timezone.utc).isoformat()
    except Exception:
        return ""

def part_to_text(data):
    """Extrae texto legible de una part. Devuelve (tipo, texto) donde tipo es 'text'|'tool'|''."""
    try:
        d = json.loads(data) if isinstance(data, str) else data
    except Exception:
        return ("", "")
    t = d.get("type", "")
    if t == "text":
        return ("text", d.get("text", "") or "")
    if t == "tool":
        tool = d.get("tool", "herramienta")
        st = d.get("state", {}) or {}
        inp = st.get("input", {}) or {}
        # resumir la herramienta
        target = inp.get("filePath") or inp.get("path") or inp.get("command") or ""
        if isinstance(target, list):
            target = " ".join(map(str, target))
        label = f"[herramienta: {tool}{(' → ' + str(target)) if target else ''}]"
        # salida de la herramienta, si está
        out = st.get("output") or st.get("result") or ""
        if isinstance(out, (dict, list)):
            out = json.dumps(out, ensure_ascii=False)
        out = str(out).strip()
        if len(out) > 500:
            out = out[:500] + " …(recortado)"
        body = label + (f"\n```\n{out}\n```" if out else "")
        return ("tool", body)
    if t == "reasoning":
        return ("", "")  # razonamiento interno: descartar
    # otros tipos: intentar texto
    if "text" in d:
        return ("text", d.get("text", "") or "")
    return ("", "")

def main():
    db_path, out_dir = sys.argv[1], sys.argv[2]
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    sessions = con.execute(
        "SELECT id, title, directory, time_created FROM session ORDER BY time_created"
    ).fetchall()

    counts = {"ok": 0, "empty": 0}
    for s in sessions:
        sid = s["id"]
        title = (s["title"] or "").strip() or ("sesion-" + sid[:12])
        directory = s["directory"] or ""
        proj = project_label(directory)
        date_iso = ms_to_iso(s["time_created"])

        # mensajes de la sesión, ordenados por tiempo
        msgs = con.execute(
            "SELECT id, data, time_created FROM message WHERE session_id=? ORDER BY time_created",
            (sid,)
        ).fetchall()

        blocks = []
        for m in msgs:
            try:
                mdata = json.loads(m["data"])
            except Exception:
                mdata = {}
            role = mdata.get("role", "")
            if role not in ("user", "assistant"):
                continue
            # parts del mensaje, ordenadas
            parts = con.execute(
                "SELECT data, time_created FROM part WHERE message_id=? ORDER BY time_created",
                (m["id"],)
            ).fetchall()
            seg_text = []
            for p in parts:
                typ, txt = part_to_text(p["data"])
                if txt and txt.strip():
                    seg_text.append(txt)
            if not seg_text:
                continue
            label = "Tú" if role == "user" else "OpenCode"
            blocks.append(f"### {label}\n\n" + "\n\n".join(seg_text) + "\n")

        if not blocks:
            counts["empty"] += 1
            continue

        pdir = os.path.join(out_dir, proj)
        os.makedirs(pdir, exist_ok=True)
        prefix = (date_iso or "0000-00-00")[:10]
        fname = f"{prefix}__{safe_filename(title)}__{sid}.md"
        with open(os.path.join(pdir, fname), "w") as o:
            o.write(f"# {title}\n\n")
            o.write(f"<!-- fecha: {date_iso} | id: {sid} | proyecto: {proj} | fuente: opencode -->\n\n")
            o.write("\n".join(blocks))
        counts["ok"] += 1

    con.close()
    print(f"Convertidas: {counts['ok']}")
    print(f"Vacías: {counts['empty']}")

    # sello de backup
    try:
        info_path = os.path.join(out_dir, "_backup-info.json")
        info = {}
        if os.path.exists(info_path):
            try: info = json.load(open(info_path))
            except Exception: info = {}
        info["opencode"] = {"generado": datetime.datetime.now().astimezone().isoformat(), "conversaciones": counts["ok"]}
        os.makedirs(out_dir, exist_ok=True)
        json.dump(info, open(info_path, "w"), ensure_ascii=False, indent=2)
    except Exception:
        pass

if __name__ == "__main__":
    main()
