---
name: session-collector
description: Collect a complete Claude Code session bundle (transcript, subagent transcripts, tool results, file-history snapshots, history lines) into a portable tar.gz archive, with optional secret redaction. Use when the user wants to archive, back up, export, share, or attach a session for a bug report, or save sessions before the 30-day auto-cleanup sweep. Trigger keywords - archive session, export session, save transcript, bundle session, session backup, share conversation.
---

# Session Collector

Bundle everything belonging to a Claude Code session into one portable
`tar.gz` for bug reports, sharing, or backup. Claude Code auto-deletes
session files older than `cleanupPeriodDays` (default 30) at startup, so
archiving is the only way to keep older sessions. All collection work is
done by `scripts/collect.py`, which streams files line-by-line — session
files can be multi-gigabyte and must NEVER be read into context.

## When invoked:

1. Determine the session UUID:
   - For the live session, check the `CLAUDE_CODE_SESSION_ID` environment
     variable: `echo $CLAUDE_CODE_SESSION_ID`.
   - Otherwise list the project's transcript dir and pick the newest file:
     `ls -t "$HOME/.claude/projects/<encoded-path>/"*.jsonl | head -5`.
     The encoded path is the absolute project path with every
     non-alphanumeric character replaced by `-`
     (`/home/user/Skills` becomes `-home-user-Skills`). `~/.claude` may be
     `/root/.claude` in sandboxes — always resolve via `$HOME`, or use
     `CLAUDE_CONFIG_DIR` if that env var is set.
   - If unsure which session the user means, show them the candidate UUIDs
     with modification times and ask.
2. Ask (or infer) whether the archive will leave the machine. If it might
   be shared, attached to an issue, or uploaded anywhere, use `--redact`.
3. RUN the script — do not read it, do not reimplement it:
   `python3 scripts/collect.py SESSION_UUID --project /path/to/project --out /tmp --redact`
   (run from this skill's directory, or use the absolute path to the script).
4. Relay the script's output: archive path, sessions bundled, payload size,
   and redaction count.

## Script flags

`python3 scripts/collect.py SESSION_UUID [flags]`

- `SESSION_UUID` — the session to collect. Optional only with `--all-project`.
- `--project PATH` — project path (real path like `/home/user/Skills`, or the
  encoded dir name). If omitted, every project dir is searched for the UUID.
- `--out DIR` — directory for the resulting archive (default: current dir).
- `--redact` — write sanitized copies into the archive, masking AWS keys,
  `ghp_`/`github_pat_` GitHub tokens, `sk-`-style API keys, Stripe keys,
  Bearer tokens, Slack tokens, PEM private-key blocks, and `password=...`
  assignments. Originals on disk are never modified.
- `--all-project` — bundle every session of the project given by `--project`.

## What goes into the bundle

- `<uuid>.jsonl` — the main transcript.
- `<uuid>/subagents/` — subagent/sidechain transcripts, if present.
- `<uuid>/tool-results/` — large tool outputs spilled to files, if present.
- `<uuid>/file-history/` — pre-edit file snapshots from
  `~/.claude/file-history/<uuid>/`, if present.
- `<uuid>/history-extract.jsonl` — lines from `~/.claude/history.jsonl`
  mentioning the session.
- `manifest.json` — session id, project dir, date range, line count,
  per-file sizes, Claude Code versions seen, redaction stats.

## Safety rules

- Transcripts are plaintext and unencrypted. Any secret a tool ever read or
  printed (env vars, keys in config files, command output) is sitting in
  them verbatim. STRONGLY recommend `--redact` whenever the archive will be
  shared, and say so explicitly in your report.
- Redaction is best-effort pattern matching; tell the user to spot-check the
  sanitized copy before sharing anything sensitive.
- Never modify or delete anything under `~/.claude/` — the script only reads
  originals and writes new files under `--out`.
- Never cat, Read, or grep the raw `.jsonl` transcripts into context; use
  the script and `ls` metadata only.

## Final report format

Report back with:
- Archive path and compressed size (`ls -lh` on the archive is fine).
- Sessions bundled, line count, and date range from the script output.
- Whether redaction was applied and how many redactions were made; if it was
  NOT applied, a one-line warning that the archive may contain secrets.
- A reminder that the bundle protects against the 30-day auto-cleanup.
