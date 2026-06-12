---
name: history-doctor
description: Inspects and repairs Claude Code's prompt history (~/.claude/history.jsonl) and the projects map in ~/.claude.json - malformed lines, stale entries for deleted projects, stale trust records. Use when the user reports broken up-arrow prompt recall, a failing claude --continue, stale or wrong project history, or asks to clean up history.jsonl or .claude.json project entries.
---

# History Doctor

Diagnoses and repairs the two persistent files behind Claude Code's prompt
history and project bookkeeping: `~/.claude/history.jsonl` (every prompt with
timestamp and project path; powers up-arrow recall and feeds `--continue` —
stale entries are a known `--continue` breaker, #10063) and the `projects` key
of `~/.claude.json` (per-project trust decisions and last-session metrics).
All checks and fixes go through a stdlib-only script that is report-only by
default and always backs up before writing.

## When invoked:

1. Resolve the config dir from `$CLAUDE_CONFIG_DIR` or `$HOME/.claude` (in
   sandboxes `$HOME` may be `/root` while the project lives under
   `/home/user/...`). `history.jsonl` lives inside it; `~/.claude.json` is the
   sibling file next to the config dir.
2. Run the report first. Always RUN the script (do not read it), with the path
   relative to this skill directory, and never read `history.jsonl` directly
   into your context (it can be very large):
   - `python3 scripts/history_doctor.py` — report only; modifies nothing. Lists
     malformed history lines by line number, history entries pointing at project
     paths that no longer exist, and `~/.claude.json` `projects` entries whose
     paths are gone (stale trust records).
   - `python3 scripts/history_doctor.py --fix` — backs up BOTH files to
     timestamped `.bak-<timestamp>` copies first, then removes malformed lines
     from `history.jsonl`. Stale-path entries are NOT touched by `--fix` alone.
   - `python3 scripts/history_doctor.py --fix --prune-missing` — additionally
     removes history entries and `projects`-map entries whose paths no longer
     exist. `--prune-missing` is deliberately a separate explicit flag and
     refuses to run without `--fix`.
3. Show the user the report. Before any `--fix`, confirm intent and warn about
   side effects (below). Before `--prune-missing`, double-check with the user
   that the "missing" paths are truly gone for good — paths on unmounted drives
   or network shares look missing but are not.
4. After fixing, report the backup paths and tell the user to verify up-arrow
   recall and `claude --continue` in a fresh session.

## Critical safety rules

- `~/.claude.json` ALSO holds OAuth credentials, global settings, and onboarding
  state. The script only ever mutates the `projects` key and writes every other
  key back untouched — never edit that file by hand or with `jq`-style rewrites
  from this skill, and never remove or alter any non-`projects` key.
- If `~/.claude.json` itself fails to parse, DO NOT auto-repair it. Point the
  user at `~/.claude/backups/` (pre-migration copies of `~/.claude.json`) or a
  re-login. Corrupting this file logs the user out.
- Always run report-only mode first; never lead with `--fix`.
- Backups are mandatory and the script creates them automatically; quote their
  exact paths in your report and tell the user to keep them until verified.
- Removing history entries permanently changes what up-arrow recall and
  `--continue` can see (#10063); removing `projects` entries means Claude Code
  will re-ask the trust prompt for those paths if they ever come back. Say both
  of these out loud before applying.

## Key background

- `history.jsonl` is append-only JSONL, one prompt per line, with the display
  text, a timestamp, and the project path. Entry shape drifts across CLI
  versions; the script reads the project path defensively (`project`, `cwd`, or
  `projectPath`).
- A stale or corrupt `history.jsonl` is a known cause of `--continue` failing
  even when `--resume <uuid>` works (#10063). If `--resume` is ALSO failing, the
  problem is the session transcript itself — route to `session-doctor` instead.
- Auto-cleanup sweeps old files under `~/.claude/` after `cleanupPeriodDays`
  (default 30), so history may legitimately reference sessions whose transcripts
  are already gone; that alone is not corruption.

## Expected output format

Report to the user:
1. **Files checked** — both paths and whether each exists/parses.
2. **history.jsonl findings** — total lines, malformed line numbers, stale-path
   entries grouped by missing path.
3. **claude.json findings** — `projects` entry count and which are stale.
4. **Action taken or proposed** — exact command for the fix, backup paths if
   applied, and the verification steps (up-arrow recall, `claude --continue`).
