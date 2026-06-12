---
name: session-format-reference
description: Authoritative reference for the Claude Code session JSONL transcript format and the ~/.claude directory layout. Use when building or debugging session tooling — parsing transcripts, computing token usage, reconstructing conversation trees, finding sessions, or answering questions about session files, .jsonl records, parentUuid trees, sidechains, toolUseResult, or summary records.
---

# Session Format Reference

A knowledge skill: the field-by-field reference for Claude Code's session
transcript format, for anyone writing tools that read, analyze, repair, or
search session files. No scripts — read the facts below, and consult
`references/format.md` (in this skill directory) for the full schema
tables, record-type details, and worked `jq` examples before writing any
parsing code.

When invoked:

1. Identify what the user is building or asking (token accounting,
   conversation reconstruction, session search, repair, etc.).
2. Read `references/format.md` for the exact field names, types, and
   caveats relevant to the task — do not guess field names from memory.
3. Apply the streaming rule below when actually touching transcript files.
4. Answer with concrete field names, record shapes, and ready-to-run `jq`
   pipelines adapted from the reference.

## Where session data lives

Everything is under `~/.claude` (resolve via `$HOME` or
`CLAUDE_CONFIG_DIR` — in sandboxes `$HOME` may be `/root` while the
workspace is under `/home/user`):

- `projects/<encoded-path>/<session-uuid>.jsonl` — the transcripts. The
  project path is encoded by replacing `/` with `-`:
  `/home/user/Skills` becomes `-home-user-Skills`.
- `projects/<encoded-path>/<session-uuid>/` — sibling directory per
  session with `subagents/` (sidechain transcripts) and `tool-results/`
  (spill files for large tool outputs).
- `file-history/<session>/` — pre-edit file snapshots.
- `history.jsonl` — the global prompt history (never auto-cleaned).
- Other dirs (`debug/`, `plans/`, `tasks/`, `shell-snapshots/`, caches)
  are not part of the transcript format.

## Record format in one paragraph

A transcript is append-only, one JSON object per line. Each line has a
`type` (`user`, `assistant`, `system`, `summary`, `attachment`,
`queue-operation`, `file-history-snapshot`, plus progress/compaction/hook
meta events), a `uuid`, and a `parentUuid` (null on roots). The lines form
a tree, not a list: rewinds and retries create branches, and a single
conversation is the path from a leaf back to the root. `user` and
`assistant` lines carry a `message` object (role + content, where content
is a string or an array of `text` / `thinking` / `tool_use` /
`tool_result` blocks); assistant messages carry `message.usage` token
counts and the model id. Structured raw tool output rides on a top-level
`toolUseResult` field of user-type lines. `summary` lines
(`{type, summary, leafUuid}`) name the leaf they summarize.

## Version drift — the cardinal caveat

The format drifts across Claude Code versions. Every line carries a
`version` field recording the version that wrote it. Tooling MUST:

- check `version` per line, not per file (files can span upgrades);
- treat unknown `type` values and unknown fields as expected, never as
  corruption — skip or pass them through;
- never require fields beyond `type`/`uuid` to be present.

## Safety and performance rules

- NEVER load a multi-MB transcript into agent context (no bare `cat` or
  full-file Read). Always stream: `jq`, `grep -c`, `head`/`tail`, or a
  line-by-line script. Check `ls -lh` / `du -h` first.
- Transcripts are plaintext and secrets land in them (env dumps, tokens
  in tool output). Treat content as sensitive; never paste raw lines
  into public reports without review.
- Treat transcripts as read-only unless the user explicitly asks for
  repair, and back up before any rewrite.
- Large tool outputs may live in the sibling `tool-results/` directory
  rather than inline — a short `tool_result` block does not mean the
  output was short.

## Quick jq cheatsheet

(Full versions and more in `references/format.md`.)

- Total output tokens:
  `jq -s 'map(.message.usage.output_tokens // 0) | add' s.jsonl`
- Record-type histogram:
  `jq -r .type s.jsonl | sort | uniq -c | sort -rn`
- Find sessions mentioning a string:
  `grep -l "needle" ~/.claude/projects/*/*.jsonl`

## Report format

When answering format questions, cite exact field names and types from
`references/format.md`, state which record types the answer applies to,
and include a runnable `jq` or script snippet when the user is building
tooling. Flag any answer that depends on version-drifting behavior.
