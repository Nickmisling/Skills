---
name: session-size-guard
description: Finds oversized or runaway Claude Code session JSONL files before they hang the CLI, shows what record types are bloating them, and recommends the right fix per file. Use when the user mentions a slow or hanging CLI, huge .claude directory, disk space problems, multi-GB session files, or asks to audit/clean up session storage size.
---

# Session Size Guard

Audits the size of Claude Code session transcripts under
`~/.claude/projects/<encoded-path>/`. Session files over 50 MB are known to hang
the CLI (#21022, #22365), and unbounded `~/.claude` growth has caused disk-full
conditions that corrupt settings and auth (#24207). The most common cause of
multi-GB files is progress-entry bloat: in issue #18905 a 3.8 GB transcript was
99.6% `progress` lines. The right fix for that is stripping those lines, NOT
deleting the session — the actual conversation underneath is usually tiny.

## When invoked:

1. Resolve the config dir from `$CLAUDE_CONFIG_DIR` or `$HOME/.claude` (in
   sandboxes `$HOME` may be `/root` while the project lives under `/home/user/...`).
2. Run the report script. NEVER read session `.jsonl` files into your context —
   they can be multi-gigabyte; the script streams them line-by-line. Always RUN
   it (do not read it), with the path relative to this skill directory:
   - `python3 scripts/size_report.py` — rank all session files across every
     project, detail-scan files at/above 50 MB.
   - `--threshold-mb N` — detail-scan files at or above N MB (lower it, e.g.
     `--threshold-mb 10`, for a stricter audit).
   - `--top N` — list the N largest files (default 20).
   - `--project PATH` — restrict to one project's sessions; `--all` is the
     explicit form of the default all-projects scan. The two are mutually
     exclusive.
3. For each flagged file the script prints a record-type histogram (count, bytes,
   percent share) plus the sizes of the sibling `<uuid>/subagents/` and
   `<uuid>/tool-results/` dirs, and a recommended action. Relay these and explain
   the reasoning (see below).
4. If the user wants to act on a recommendation, hand off: progress-stripping and
   line-level fixes belong to the `session-repair` skill
   (`repair.py FILE --apply --strip-progress`); this skill itself never modifies
   anything.

## Key background

- Why 50 MB matters: the CLI parses the full transcript on resume/startup; files
  beyond ~50 MB make it hang or become unusable (#21022, #22365). Treat anything
  over that as critical, 10-50 MB as worth watching.
- Progress bloat (#18905): some versions wrote a flood of `progress`-type
  telemetry lines into the transcript. They carry no conversation content, so
  stripping them is lossless for resume purposes. Recommend strip, not delete.
- Large `user` lines usually mean huge `toolUseResult` payloads (raw tool output
  is stored top-level on user lines); large `attachment` lines mean pasted
  files/images. For these, archiving (gzip elsewhere) then deleting is the
  remedy IF the user no longer needs to resume the session.
- Each session also has a sibling `<uuid>/` dir holding `subagents/` (subagent
  transcripts) and `tool-results/` (large tool outputs spilled to files) — these
  count toward disk usage too. Other growth areas under `~/.claude/`:
  `file-history/`, `paste-cache/`, `image-cache/`, `shell-snapshots/`, `debug/`.
  Auto-cleanup sweeps files older than `cleanupPeriodDays` (default 30) at
  startup, so chronic growth means files younger than that window.

## Safety rules

- This skill is STRICTLY READ-ONLY. Never delete, truncate, gzip, or move session
  files yourself from this skill — only report and recommend.
- If deletion is recommended and the user agrees, tell them to archive first
  (e.g. `gzip -c FILE > /safe/place/FILE.gz`) and to remove the sibling
  `<uuid>/` dir together with `<uuid>.jsonl` — leaving one without the other
  creates the orphaned-dir resume failure (#18311).
- Never repair files here; route to `session-repair` for any modification.

## Expected output format

Report to the user:
1. **Totals** — file count and total bytes scanned, scope, thresholds used.
2. **Top-N table** — size, session uuid, project, over-50 MB flags.
3. **Per-oversized-file breakdown** — dominant record types with percent shares,
   sibling dir sizes, and the recommended action in plain language.
4. **Next steps** — exact follow-up commands (e.g. the session-repair invocation
   with `--strip-progress`) and which files to handle first.
