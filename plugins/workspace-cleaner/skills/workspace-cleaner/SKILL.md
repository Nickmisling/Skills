---
name: workspace-cleaner
description: Audit and safely reclaim disk space in the ~/.claude data directory — old transcripts, debug logs, orphaned session artifacts, stale shell snapshots, and legacy directories. Use when the user mentions ".claude is huge", "Claude Code eating disk space", "clean up old sessions", "purge transcripts", "disk full", or wants to know what is safe to delete in ~/.claude.
---

# Workspace Cleaner

Audits the `~/.claude` data directory and reclaims disk space safely. The
directory accumulates session transcripts, pre-edit file snapshots, debug
logs, and caches; real-world installs reach 1.8 GB+ and 10k+ files, and
debug logs alone have been reported at 3 GB+. A full disk can corrupt
settings and auth state, so periodic cleanup matters — but several files
in `~/.claude` are load-bearing and must never be touched.

When invoked:

1. Run the read-only audit first (relative to this skill directory):
   `python3 scripts/audit.py` (optionally `--threshold-days N`, default 30).
   Run the script — do not read it.
2. Present the report to the user: per-directory sizes, per-project session
   counts and ages, top-10 largest files, orphaned artifacts, stale shell
   snapshots, and legacy directories.
3. Ask which categories the user wants cleaned. Never assume. Each category
   is a separate opt-in flag.
4. Preview the deletion with a dry run (the default), e.g.:
   `python3 scripts/clean.py --legacy --debug-logs --orphans --stale-snapshots 30`
   Show the user exactly what would be deleted and how much space it frees.
5. Only after the user explicitly confirms, re-run the same command with
   `--apply`.
6. For removing a whole project's history, first check the CLI version
   (`claude --version`). If it is 2.1.124 or newer, prefer the official
   command: `claude project purge <path> --dry-run`, then without
   `--dry-run` once confirmed — it also cleans `history.jsonl` lines and
   the `~/.claude.json` project entry, which the script cannot safely do.
   Otherwise fall back to `scripts/clean.py --project=ENCODED_NAME`
   (encoding: `/` becomes `-`, e.g. `/home/user/Skills` is
   `-home-user-Skills`; use the `=` form because the name's leading `-`
   would otherwise be parsed as a flag).
7. Suggest prevention: setting `cleanupPeriodDays` in settings (default 30)
   controls the automatic sweep of old transcripts at startup.

## Background

- `projects/<encoded-path>/<session-uuid>.jsonl` holds transcripts; sibling
  `<uuid>/` directories hold `subagents/` and `tool-results/`. A `<uuid>/`
  dir with no matching `.jsonl` is an orphan.
- `file-history/<session>/` holds pre-edit snapshots; entries for sessions
  whose transcript is gone are orphans.
- `debug/` can grow to multiple GB and is safe to clear.
- `paste-cache/` and `image-cache/` are regenerable caches.
- `shell-snapshots/` captures shell state for the Bash tool. Snapshots
  belonging to live sessions must NEVER be deleted — the script skips any
  snapshot matching the current `CLAUDE_CODE_SESSION_ID` and anything
  newer than the staleness threshold.
- `todos/`, `statsig/`, `logs/` are legacy directories no longer written.
- `backups/` holds pre-migration copies of `~/.claude.json`; treat as a
  last-resort recovery resource and only delete with explicit consent.
- `~/.claude` may live at `/root/.claude` in sandboxes while the cwd is
  under `/home/user`; the scripts resolve it via `CLAUDE_CONFIG_DIR` or
  `$HOME`, never the cwd.

## Safety rules

- NEVER delete or edit `~/.claude.json` (OAuth tokens, per-project trust,
  settings), `settings.json`, `CLAUDE.md`, or the `plugins/`, `skills/`,
  `agents/`, `commands/` directories.
- NEVER auto-clean `history.jsonl`, `stats-cache.json`, or
  `remote-settings.json`.
- NEVER delete shell snapshots of live sessions.
- Always dry-run first; `--apply` only after explicit per-category user
  confirmation. Do not invent extra deletion targets beyond what the
  script reports.

## Report format

Present results as: total size, then a table of category / size / file
count / recommendation (safe to clean, needs confirmation, never touch),
then the exact `clean.py` command you propose and the space it would free.
