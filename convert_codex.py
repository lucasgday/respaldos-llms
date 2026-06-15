#!/usr/bin/env python3
"""Convierte sesiones de Codex (rollout-*.jsonl) a Markdown legible.
Cruza con session_index.jsonl para título (thread_name) y usa session_meta para fecha/proyecto.
Uso: convert_codex.py <carpeta_sessions> <session_index.jsonl> <carpeta_salida>
"""
import json, os, re, sys, glob

def load_index(index_path):
    idx = {}
    if not os.path.exists(index_path):
        return idx
    for line in open(index_path):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if "id" in d:
            idx[d["id"]] = {
                "title": d.get("thread_name"),
                "updated_at": d.get("updated_at"),
            }
    return idx

def text_from_content(content):
    """content es una lista de bloques {type, text}. Devuelve texto plano."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for c in content:
        if isinstance(c, dict):
            # input_text / output_text / text
            t = c.get("text")
            if t:
                parts.append(t)
        elif isinstance(c, str):
            parts.append(c)
    return "\n".join(p for p in parts if p)

def fmt_function_call(payload):
    name = payload.get("name", "tool")
    args = payload.get("arguments", "")
    try:
        a = json.loads(args) if isinstance(args, str) else args
        if isinstance(a, dict) and "command" in a:
            cmd = a["command"]
            if isinstance(cmd, list):
                cmd = " ".join(cmd)
            return f"[herramienta: {name}]\n```bash\n{cmd}\n```"
        blob = json.dumps(a, ensure_ascii=False)
    except Exception:
        blob = str(args)
    if len(blob) > 300:
        blob = blob[:300] + " …"
    return f"[herramienta: {name} {blob}]"

def fmt_function_output(payload):
    out = payload.get("output", "")
    if isinstance(out, (dict, list)):
        out = json.dumps(out, ensure_ascii=False)
    out = str(out).strip()
    if len(out) > 500:
        out = out[:500] + " …(recortado)"
    return f"[resultado]\n```\n{out}\n```" if out else ""

def msg_to_md(role, content):
    txt = text_from_content(content)
    if not txt.strip():
        return None
    label = "Tú" if role == "user" else "Codex"
    return f"### {label}\n\n{txt}\n"

def parse_session(path, index, archived=False):
    sid = None
    sess_ts = None
    cwd = None
    blocks = []

    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        typ = d.get("type")
        payload = d.get("payload", {})

        if typ == "session_meta":
            sid = payload.get("id")
            sess_ts = payload.get("timestamp")
            cwd = payload.get("cwd")

        elif typ == "response_item":
            ptype = payload.get("type")
            if ptype == "message":
                role = payload.get("role")
                if role in ("user", "assistant"):
                    md = msg_to_md(role, payload.get("content", []))
                    if md:
                        blocks.append(md)
                # developer / system → se ignoran (instrucciones internas)
            elif ptype == "function_call":
                blocks.append("### Codex\n\n" + fmt_function_call(payload) + "\n")
            elif ptype == "function_call_output":
                out = fmt_function_output(payload)
                if out:
                    blocks.append("### Codex\n\n" + out + "\n")
            # reasoning → se ignora (razonamiento interno)

        elif typ == "compacted":
            # rescatar historial que el compactado reemplazó
            for m in payload.get("replacement_history", []):
                if isinstance(m, dict) and m.get("type") == "message":
                    role = m.get("role")
                    if role in ("user", "assistant"):
                        md = msg_to_md(role, m.get("content", []))
                        if md:
                            blocks.append(md)

    # título: del índice si existe, si no, del primer mensaje de usuario, si no, fecha
    meta = index.get(sid, {}) if sid else {}
    title = meta.get("title")
    updated = meta.get("updated_at") or sess_ts
    if not title:
        # buscar primer "### Tú"
        for b in blocks:
            if b.startswith("### Tú"):
                first = b.split("\n\n", 1)[1] if "\n\n" in b else ""
                first = first.strip().split("\n")[0]
                if first:
                    title = first[:70]
                    break
    if not title:
        title = "sesion-" + (sid or os.path.basename(path))[:20]

    project = ""
    if cwd:
        project = os.path.basename(cwd.rstrip("/"))

    return {
        "id": sid,
        "title": title,
        "date": (updated or "")[:10],
        "datetime": updated or "",
        "project": project,
        "blocks": blocks,
        "archived": archived,
    }

def safe_filename(s):
    s = re.sub(r"[^\w\s-]", "", s).strip().replace(" ", "_")
    return s[:80] or "sesion"

def main():
    sessions_dir, index_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    archived = len(sys.argv) > 4 and sys.argv[4].lower() in ("1","true","archived","yes")
    index = load_index(index_path)
    files = glob.glob(os.path.join(sessions_dir, "**", "*.jsonl"), recursive=True)

    counts = {"ok": 0, "empty": 0}
    seen_names = {}
    for f in files:
        s = parse_session(f, index, archived=archived)
        if not s["blocks"]:
            counts["empty"] += 1
            continue
        proj = s["project"] or "sin-proyecto"
        pdir = os.path.join(out_dir, proj)
        os.makedirs(pdir, exist_ok=True)

        base = safe_filename(s["title"])
        # prefijo de fecha (orden cronológico) + sufijo de UUID corto (unicidad garantizada)
        prefix = (s["date"] or "0000-00-00")
        uid = (s["id"] or "") or os.path.splitext(os.path.basename(f))[0]
        fname = f"{prefix}__{base}__{uid}.md"

        with open(os.path.join(pdir, fname), "w") as out:
            out.write(f"# {s['title']}\n\n")
            out.write(f"<!-- fecha: {s['datetime']} | id: {s['id']} | proyecto: {proj} | fuente: codex | archivada: {str(s['archived']).lower()} -->\n\n")
            out.write("\n".join(s["blocks"]))
        counts["ok"] += 1

    print(f"Convertidas: {counts['ok']}")
    print(f"Vacías (sin mensajes legibles): {counts['empty']}")

    # sello de backup: fecha de esta corrida
    try:
        import datetime
        info_path = os.path.join(out_dir, "_backup-info.json")
        info = {}
        if os.path.exists(info_path):
            try: info = json.load(open(info_path))
            except Exception: info = {}
        key = "codex-archivadas" if archived else "codex"
        info[key] = {"generado": datetime.datetime.now().astimezone().isoformat(), "conversaciones": counts["ok"]}
        os.makedirs(out_dir, exist_ok=True)
        json.dump(info, open(info_path, "w"), ensure_ascii=False, indent=2)
    except Exception:
        pass

if __name__ == "__main__":
    main()
