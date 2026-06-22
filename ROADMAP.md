# Roadmap

Where trailkeep is headed. These are **directions, not promises** — and they all
keep the core rule: everything stays local, nothing is uploaded.

Feedback and PRs very welcome — open an issue if you'd use one of these (or want
something that isn't here).

## Planned

- **Per-conversation summaries.** A short summary at the top of each conversation
  so you can skim instead of re-reading every reply.
- **Per-project review layer.** Project home should grow into a local review
  workflow: a copyable review prompt per project, a local tasks/to-do sidecar per
  project, a global to-do view across projects, and optional prompts such as
  "build this project's design system" from its own conversation history.
- **Project visibility controls.** Hide/archive whole projects, keep that state in
  the progress export/import flow, and offer a drawer to recover hidden or
  archived projects without losing their conversations.
- **Deployment link coverage.** Keep expanding optional `deploy_url` detection from
  safe local sources such as project config files, `.vercel/project.json`, or
  locally cached deployment metadata.
- **Recommended `AGENTS.md` / `CLAUDE.md`.** Derived from your own conversations —
  your style, preferences and recurring asks — so you stop re-explaining them in
  every repo. Per-project and global.

## Exploring

- Richer **local insights** (productivity rhythms, heuristic prompt/test quality)
  building on the Evidence Ledger — all computed on-device.
- **Search across your archive**, optionally AI-assisted, over one or all projects.
- **Windows support** *(help wanted)*. The converters and viewer already run
  cross-platform; it needs a Python rewrite of the bash orchestrator, Windows
  paths, and Task Scheduler for the daily task.

## How processing would work (privacy first)

Any of the above that needs an LLM would run through **your own** model — your
IDE's agent (Claude Code, Codex, …) or your own API key — and write its results
as local sidecar files the viewer reads. No data leaves your machine; you choose
the model.

## Done

- Multi-tool backup (Claude Code, Codex, Cursor, OpenCode, Cowork) → Markdown
- Standalone, bilingual (EN/ES) viewer with grouping, search, analytics
- Incremental + cumulative; daily automatic backup; portable Markdown history
- **macOS & Linux** — per-OS source paths; `launchd` (macOS) / `cron` (Linux)
- **Evidence Ledger** — deterministic local metrics (tokens by model, tool/test/build
  counts, files modified, errors), computed on-device; nothing uploaded
