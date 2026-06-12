---
name: session-repair
description: Repairs a damaged Claude Code session JSONL file so it can be resumed - drops corrupt lines, removes the empty-content-block corruption, strips progress bloat, and re-stitches parentUuid chains, always with a backup. Use when the user says a session is corrupted, unresumable, rejected by the API on resume, or asks to fix/shrink/repair a session transcript.
---

# Session Repair

Fixes the known corruption patterns in Claude Code session transcripts
(`~/.claude/projects/<encoded-path>/<session-uuid>.jsonl`) so `claude --resume`
works again. All work is done by a streaming, stdlib-only script that defaults to
a dry run and always writes a timestamped backup before changing anything.

## When invoked:

1. Identify the target file. Resolve the config dir from `$CLAUDE_CONFIG_DIR` or
   `$HOME/.claude` (in sandboxes `$HOME` may be `/root` while the project is under
   `/home/user/...`). The project dir name is the absolute project path with `/`
   and separators replaced by `-` (e.g. `/home/user/Skills` →
   `-home-user-Skills`). If you only have a session uuid, the file is
   `<config>/projects/<encoded>/<uuid>.jsonl`.
2. SAFETY CHECK — never repair a live session. Compare the target uuid against
   `$CLAUDE_CODE_SESSION_ID` (the current session's id). If they match, or the
   file was modified in the last few minutes while a `claude` process is running,
   STOP and tell the user to repair it from a different session or after exiting.
3. Always diagnose first. If the `session-doctor` skill is available, run its
   diagnosis; otherwise run this skill's script WITHOUT `--apply` (dry run) and
   review the report. NEVER read the JSONL into your context — these files can be
   multi-gigabyte. Always RUN the script (do not read it), with the path relative
   to this skill directory:
   - `python3 scripts/repair.py /path/to/session.jsonl` — dry run: prints exactly
     what would be kept, patched, and dropped. Modifies nothing.
   - `python3 scripts/repair.py /path/to/session.jsonl --apply` — copies the file
     to `FILE.bak-<timestamp>` first, then atomically replaces it with the
     repaired version.
   - `--strip-progress` — additionally drop all `progress`-type lines. Use this
     when the dry run or session-doctor shows progress-entry bloat (issue #18905:
     a 3.8 GB transcript that was 99.6% progress lines; files over 50 MB hang the
     CLI per #21022/#22365). Progress lines are telemetry, not conversation —
     stripping them never loses user/assistant content.
4. Show the user the dry-run summary and get their go-ahead (or proceed if they
   already asked for the fix), then re-run with `--apply` (plus
   `--strip-progress` if warranted).
5. Verify and report. Tell the user to test with `claude --resume <uuid>` and how
   to roll back (`cp FILE.bak-<timestamp> FILE`). Keep the backup — never delete it.

## What the script fixes

- Unparseable JSON lines: dropped (partial/interrupted appends).
- Empty text blocks (and empty UNSIGNED thinking blocks) inside
  `message.content`: removed; if a line's content becomes empty (or already was
  `""`/`[]`), the line is dropped. This is the #41992 corruption — an empty text
  block written during thinking streaming makes the session permanently
  unresumable because the API rejects the replayed block. Empty thinking blocks
  that carry a `signature` are normal in current transcripts and are kept.
- `progress` lines: dropped only with the explicit `--strip-progress` flag.
- parentUuid re-stitching: records form a tree via `uuid`/`parentUuid` (a
  conversation is a leaf-to-root path). When a line is dropped, every child that
  pointed at it is re-pointed (transitively) at the dropped line's own parent, so
  the tree stays connected and resume still finds a complete path.

## Safety rules

- NEVER run `--apply` on the current live session (check `CLAUDE_CODE_SESSION_ID`).
- ALWAYS dry-run first; never skip straight to `--apply`.
- ALWAYS keep the `.bak-<timestamp>` file; mention its exact path in your report.
- Never edit session files by hand or with ad-hoc shell one-liners; only use the
  script (it streams line-by-line and never loads the whole file into memory).
- Do not touch `~/.claude.json`, `history.jsonl`, or anything outside the one
  target file. If resume still fails after repair because the `<uuid>/` sibling
  dir or path encoding is the problem (#18311/#33912/#45753), send the user back
  to `session-doctor` — that is not fixable by rewriting the JSONL.

## Expected output format

Report to the user:
1. **Target** — file path, size, and confirmation it is not the live session.
2. **Dry-run findings** — counts of kept/patched/dropped lines with reasons.
3. **Action taken** — backup path, new file size, percent reduction.
4. **Verification** — the exact `claude --resume <uuid>` command and the exact
   rollback command using the backup.
