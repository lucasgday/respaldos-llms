# AGENTS.md

Context for AI agents (and humans) working on **trailkeep** — a local, self-hosted
backup + viewer for your AI-coding-tool conversations (Claude Code, Codex, Cursor,
OpenCode, Cowork). macOS and Linux (paths resolved per-OS; Cowork is macOS-only).

## Non-negotiable rules

1. **Privacy is the product. The viewer makes ZERO network calls.** Never add
   `fetch`, `XMLHttpRequest`, `sendBeacon`, WebSockets, analytics/telemetry, or
   external resources (no CDN scripts/fonts) to `viewer.html`. The scripts only
   read local files and write local Markdown. Nothing — raw or derived — may leave
   the user's machine. This is the whole pitch; don't break it.
2. **English only in code** — comments and identifiers. Two deliberate exceptions,
   do NOT "fix" them:
   - the `es:` block of the `I18N` dictionary in `viewer.html` (the Spanish UI
     translation), and
   - **legacy Spanish data keys** the parser accepts for backward-compat with
     older backups: `fecha/proyecto/fuente/archivada` and the turn/tool markers
     `Tú/herramienta/resultado`, plus `generado/conversaciones`. Keep these.
3. **Cumulative, never destructive.** The backup never deletes already-generated
   markdowns, even if the source tool removed the original.

## Layout

- `update-backup.sh` — orchestrator / CLI entrypoint (`--help`, `--only`,
  `--dry-run`, optional `[OUTPUT_DIR]`). Reads each source, calls the converters.
  **Loud health detection:** these tools store conversations in private, undocumented
  locations/formats, so a vendor moving a folder or changing a format must never fail
  silently. `run_convert` warns if a converter errors or — given new/changed raw —
  converts 0 sessions; `warn_missing` warns when a source folder is gone but markdowns
  exist for it. Warnings are tallied (`HEALTH_WARN`), summarized at the end, and added
  to the desktop notification. Existing markdowns are never lost (rule #3); the risk it
  guards is NEW data silently not being captured.
- `converters/convert_*.py` — one per source (claude/codex/opencode/cursor; cowork
  reuses convert_claude). Each reads its origin and writes the standard Markdown.
- `converters/extract_ledger.py` — **Evidence Ledger**: deterministic, $0, on-device
  metrics (token usage by model, tool/test/build counts, files modified, errors)
  read from each tool's RAW storage. One scanner per format (claude+cowork .jsonl,
  codex rollouts, opencode/cursor SQLite); all emit the same per-session dict.
  Cursor carries no tokens → counts only. **Markdown fallback:** the tools prune old
  raw transcripts, but the `.md` backup is cumulative — so for sessions whose raw is
  gone, counts are parsed from the `.md` (tokens/model only exist in raw). Each
  source writes a per-source `_ledger.json` (the viewer reads every one and
  aggregates). No LLM, no network.
  Incremental: per-session metrics are cached in `_ledger-cache.json` (validated by
  size:mtime) — file sources re-scan only changed sessions; DB sources re-scan only
  when the DB changed. **Cumulative + portable (rule #3):** a session stays in the
  ledger as long as its `.md` exists; metrics measured from raw are carried forward
  from the cache, so token data persists in the data folder and travels with the
  markdowns even after the tool prunes the raw. Called from each source's block in
  `update-backup.sh`. The Claude scan reads multiple raw roots (os.pathsep-joined)
  and dedups by session uuid; `TRAILKEEP_CLAUDE_RAW_EXTRA` points at recovered-raw
  archive folders — read once to seed token data, optional thereafter.
- `converters/extract_projects.py` — **Project metadata**: deterministic, $0,
  on-device. Reads each project's `cwd` from the raw, then its git branch / last
  commit, detected stack (manifests/source hints) and status (active/inactive/gone by
  last-30-days activity or deployed state), plus safe local `repo_url` /
  `deploy_url` hints when available.
  Writes a `_projects.json` sidecar the viewer joins with the ledger (by project
  name) to render a project home. Local reads only (git, manifests/source/deploy
  hints); no network.
  Cowork runs in throwaway sandboxes with random Docker-style `cwd`s, so it folds
  into one **virtual** "cowork" project (no filesystem facts, never "gone"),
  matching the converter which tags every Cowork session `project: cowork`.
- `viewer.html` — standalone, bilingual (EN/ES) viewer. Pure reader. No build step.
- `*.command` — double-click launchers (install/uninstall the launchd task; run).
- `docs/` — `index.html` (the GitHub Pages live demo, sample data baked in),
  screenshots, `hero.gif`.
- `ROADMAP.md` — public roadmap. `ROADMAP.private.md` — maintainer-only strategy &
  full vision (gitignored via `*.private.md`; not in clones).

## Standard Markdown format (converters ↔ viewer contract)

Converters emit, and the viewer parses, exactly this:

```
# <title>

<!-- date: <ISO> | id: <id> | project: <project> | source: <source> | archived: <true|false> -->

### You

…

### <Assistant>      (Claude / Codex / Cursor / OpenCode)

…
```

Tool calls render as `[tool: <name> → …]` / `[result]` blocks. If you change the
format, update **both** the converters and the viewer's parser, and keep reading
the legacy Spanish keys (rule 2).

## Adding a source

Write a `converters/convert_<tool>.py` that reads that tool's storage and emits the
format above, then wire a block into `update-backup.sh`. The viewer needs no
changes. See any existing converter as a reference.

## Verifying changes

- Shell: `bash -n update-backup.sh *.command`
- Converters: `python3 -m py_compile converters/convert_*.py converters/extract_ledger.py`
- Viewer JS parses: `node -e "const h=require('fs').readFileSync('viewer.html','utf8');new Function(h.match(/<script>([\s\S]*)<\/script>/)[1]);console.log('ok')"`
- Visual: serve a folder of sample `.md` and open the viewer headless, or open
  `viewer.html` and point it at a markdown folder. The viewer must render with no
  console errors and make no network requests.

## i18n

UI strings live in the `I18N` dictionary (`en`/`es`) in `viewer.html`; use `t(key)`
(or `T(key)` inside turn loops where `t` is shadowed). Add new strings to **both**
languages. Language auto-detects from the browser and is user-toggleable.

## Roadmap

See [ROADMAP.md](ROADMAP.md). Post-launch direction (Linux vs the summary/AGENTS.md
pipeline) is feedback-driven; details and strategy are in the maintainer's private
notes.
