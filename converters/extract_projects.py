#!/usr/bin/env python3
"""Project metadata — deterministic, $0, on-device.

Maps each project (by its working-directory basename) to its filesystem facts:
git branch + last commit, detected stack, and whether the directory still exists.
The viewer joins this with the per-project ledger metrics to render a project home.

The viewer is a pure reader (no shell/git), so the backup computes this and writes a
`_projects.json` sidecar next to the markdowns. No network: only local reads of the
project dirs (git, manifest files) and the raw transcripts (for the cwd).

Usage: extract_projects.py <out_dir> [claude=<dir>] [cowork=<dir>] [codex=<dir>] [opencode=<db>]
  Each source is scanned only for the project working directory (cheap: the cwd is
  on the first lines). Cursor is skipped — its store carries no project path.
"""
import json, os, re, sys, glob, subprocess, datetime

# Manifest file -> stack label. First match(es) win; a project can have several.
MANIFESTS = [
    ("package.json", "node"), ("deno.json", "deno"), ("tsconfig.json", "typescript"),
    ("pyproject.toml", "python"), ("requirements.txt", "python"), ("setup.py", "python"),
    ("Cargo.toml", "rust"), ("go.mod", "go"), ("Gemfile", "ruby"),
    ("pom.xml", "java"), ("build.gradle", "java"), ("composer.json", "php"),
    ("Package.swift", "swift"), ("pubspec.yaml", "dart"), ("Dockerfile", "docker"),
]
# Hints that a project is deployed somewhere (local read, no network).
DEPLOY_HINTS = ["vercel.json", "netlify.toml", "fly.toml", ".github/workflows",
                "Procfile", "render.yaml", "wrangler.toml"]


def first_cwd_claude(path):
    """First `cwd` and timestamp in a Claude/Cowork .jsonl (usually line 1)."""
    cwd = ts = None
    for line in open(path, errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        ts = ts or d.get("timestamp")
        if d.get("cwd"):
            return d["cwd"], (d.get("timestamp") or ts)
    return None, ts


def first_cwd_codex(path):
    for line in open(path, errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("type") == "session_meta":
            p = d.get("payload", {}) or {}
            return p.get("cwd"), p.get("timestamp")
    return None, None


def add(projects, cwd, ts, source):
    """Tally a (cwd, timestamp, source) observation under the project basename."""
    if not cwd:
        return
    name = os.path.basename(cwd.rstrip("/")) or cwd
    p = projects.setdefault(name, {"paths": {}, "last": None, "sources": set()})
    p["paths"][cwd] = p["paths"].get(cwd, 0) + 1
    p["sources"].add(source)
    if ts and (p["last"] is None or ts > p["last"]):
        p["last"] = ts


def scan_claude(root, source, projects):
    for r, _d, fnames in os.walk(root):
        if os.sep + "subagents" in r + os.sep:
            continue
        for b in fnames:
            if not b.endswith(".jsonl") or b.startswith("agent-") or b == "audit.jsonl":
                continue
            try:
                cwd, ts = first_cwd_claude(os.path.join(r, b))
            except Exception:
                continue
            add(projects, cwd, ts, source)


def scan_codex(root, projects):
    for f in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
        try:
            cwd, ts = first_cwd_codex(f)
        except Exception:
            continue
        add(projects, cwd, ts, "codex")


def scan_opencode(db, projects):
    import sqlite3
    try:
        con = sqlite3.connect(db)
        rows = con.execute("SELECT directory, time_created FROM session").fetchall()
        con.close()
    except Exception:
        return
    for directory, tc in rows:
        ts = None
        try:
            if tc:
                ts = datetime.datetime.fromtimestamp(int(tc) / 1000, datetime.timezone.utc).isoformat()
        except Exception:
            ts = None
        add(projects, directory, ts, "opencode")


def git_info(path):
    if not os.path.isdir(os.path.join(path, ".git")):
        return None
    def g(*args):
        try:
            return subprocess.run(["git", "-C", path, *args], capture_output=True,
                                  text=True, timeout=4).stdout.strip()
        except Exception:
            return ""
    branch = g("rev-parse", "--abbrev-ref", "HEAD")
    last = g("log", "-1", "--format=%cs\t%s")
    date, _, msg = last.partition("\t")
    dirty = bool(g("status", "--porcelain"))
    return {"branch": branch or None, "last_commit_date": date or None,
            "last_commit_msg": (msg[:120] or None), "dirty": dirty}


def detect_stack(path):
    out = []
    for fname, label in MANIFESTS:
        if os.path.exists(os.path.join(path, fname)) and label not in out:
            out.append(label)
    return out


def is_deployed(path):
    return any(os.path.exists(os.path.join(path, h)) for h in DEPLOY_HINTS)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out_dir = sys.argv[1]
    srcs = {}
    for a in sys.argv[2:]:
        k, _, v = a.partition("=")
        if v:
            srcs[k] = v

    projects = {}
    if "claude" in srcs and os.path.isdir(srcs["claude"]):
        scan_claude(srcs["claude"], "claude-code", projects)
    if "cowork" in srcs and os.path.isdir(srcs["cowork"]):
        scan_claude(srcs["cowork"], "cowork", projects)
    if "codex" in srcs and os.path.isdir(srcs["codex"]):
        scan_codex(srcs["codex"], projects)
    if "opencode" in srcs and os.path.isfile(srcs["opencode"]):
        scan_opencode(srcs["opencode"], projects)

    now = datetime.datetime.now(datetime.timezone.utc)
    out = {}
    for name, p in projects.items():
        # the most-used cwd wins (handles a project opened from a few paths)
        path = max(p["paths"].items(), key=lambda kv: kv[1])[0]
        exists = os.path.isdir(path)
        git = git_info(path) if exists else None
        # status: active if touched in the last 21 days, else inactive; gone if the
        # directory no longer exists.
        status = "gone" if not exists else "inactive"
        last = p["last"]
        if exists and last:
            try:
                d = datetime.datetime.fromisoformat(last.replace("Z", "+00:00"))
                if d.tzinfo is None:
                    d = d.replace(tzinfo=datetime.timezone.utc)
                status = "active" if (now - d).days <= 21 else "inactive"
            except Exception:
                pass
        out[name] = {
            "path": path, "exists": exists, "status": status,
            "last_activity": last, "sources": sorted(p["sources"]),
            "git": git, "stack": detect_stack(path) if exists else [],
            "deployed": is_deployed(path) if exists else False,
        }

    doc = {"generated": datetime.datetime.now().astimezone().isoformat(), "projects": out}
    os.makedirs(out_dir, exist_ok=True)
    json.dump(doc, open(os.path.join(out_dir, "_projects.json"), "w"),
              ensure_ascii=False, indent=2)
    actives = sum(1 for v in out.values() if v["status"] == "active")
    print(f"Projects: {len(out)} ({actives} active, "
          f"{sum(1 for v in out.values() if v['exists'])} on disk)")


if __name__ == "__main__":
    main()
