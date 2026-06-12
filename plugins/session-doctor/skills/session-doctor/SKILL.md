---
name: session-doctor
description: Diagnoses Claude Code session and resume problems by validating session JSONL transcripts, parent chains, and project-path encoding. Use when the user reports "No conversation found", a failing claude --resume or --continue, a hanging or slow CLI, corrupted/unresumable sessions, or asks to check session health.
---

# Session Doctor

Read-only diagnosis of Claude Code session storage. Session transcripts live at
`~/.claude/projects/<encoded-path>/<session-uuid>.jsonl` and a handful of known
corruption patterns make them unresumable or hang the CLI. This skill locates the
right files, validates them with a streaming script, and maps every finding to the
known upstream issue so the user understands what happened and what to do next.

## When invoked:

1. Resolve the Claude config dir. It is `$CLAUDE_CONFIG_DIR` if set, otherwise
   `$HOME/.claude`. CAUTION: in sandboxes `$HOME` may be `/root` while the project
   lives under `/home/user/...` — always resolve via `$HOME`/`CLAUDE_CONFIG_DIR`,
   never hardcode `~/.claude` literally.
2. Compute the expected encoded project dir: take the absolute project path and
   replace every `/` and non-alphanumeric separator with `-` (e.g.
   `/home/user/Skills` becomes `-home-user-Skills`). Compare against what actually
   exists under `<config>/projects/` (`ls` it). A near-miss means a path-encoding
   mismatch — commonly caused by a symlinked cwd or a symlinked `.git` directory
   (issues #18311, #33912, #45753). Check with `ls -ld <project>/.git` whether
   `.git` is a symlink.
3. Run the diagnostic script. NEVER read session `.jsonl` files directly into your
   context — they can be multi-gigabyte. Always run the script instead, with paths
   relative to this skill directory:
   - `python3 scripts/diagnose.py` — scan every session of the current project.
   - `python3 scripts/diagnose.py SESSION_UUID` — diagnose one session (searches
     this project, then all projects, and detects orphaned `<uuid>/` dirs).
   - `python3 scripts/diagnose.py /path/to/file.jsonl` — diagnose a specific file.
   - `--project PATH` — resolve sessions against PATH instead of the cwd.
4. Interpret the report and explain each finding (see mapping below).
5. If repairs are needed, recommend the `session-repair` skill — do NOT modify
   anything yourself from this skill.

## What the script detects, and which known issue it maps to

- Malformed JSON lines (with line numbers) — partial writes or interrupted appends.
- Empty text blocks / empty `message.content` — issue #41992: an empty text
  block written during thinking streaming makes the session permanently
  unresumable because the API rejects the replayed block on resume. (Empty
  thinking blocks that carry a `signature` are normal and reported as INFO only.)
- Broken `parentUuid` chains (parents referenced but never defined) — records form
  a tree via `uuid`/`parentUuid`; a conversation is the leaf-to-root path. Missing
  parents lose rewind/branch history.
- Orphaned session dirs — a `<uuid>/` sibling dir (holding `subagents/` and
  `tool-results/`) exists but `<uuid>.jsonl` is gone: the classic
  "No conversation found" cause (#18311). Files older than `cleanupPeriodDays`
  (default 30) are swept at startup, which can also remove transcripts.
- Size: >50 MB is critical (hangs the CLI, #21022/#22365); >10 MB is a warning.
- Record-type histogram with per-type bytes — flags progress-entry bloat (#18905:
  a 3.8 GB file that was 99.6% progress lines).

Other background: each JSONL line has `type` (user, assistant, system, summary,
attachment, queue-operation, file-history-snapshot, progress, ...), `uuid`,
`parentUuid`, `sessionId`, ISO-8601 `timestamp`, `isSidechain`, `cwd`, `gitBranch`,
and a `version` field (format drifts across versions). If sessions exist but the
writer stopped appending after a CLI upgrade, that is #53417. If `--continue`
fails while `--resume <uuid>` works, suspect stale `~/.claude/history.jsonl`
(#10063) and recommend the `history-doctor` skill.

## Safety rules

- This skill is STRICTLY READ-ONLY. Never edit, move, delete, or truncate any file
  under the config dir. The script itself never writes.
- Never `cat`/Read a session JSONL into context; only use the script's summary.
- Do not run repairs here; hand off to `session-repair` with the exact file path.

## Expected output format

Report to the user:
1. **Paths checked** — config dir, expected encoded dir, whether it exists.
2. **Per-session table** — uuid, size, line count, health (OK / WARN / CRITICAL).
3. **Findings** — each issue in plain language, with the matching GitHub issue
   number and the affected line numbers.
4. **Recommended next step** — e.g. "run session-repair on FILE", "strip progress
   entries", "check the .git symlink", or "session is healthy; the resume failure
   is a path-encoding mismatch".
