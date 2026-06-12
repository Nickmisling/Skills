---
name: session-search
description: Find past Claude Code sessions across all projects by keyword and date range, list projects with session inventories, and extract any session as readable Markdown or JSON. Use when the user asks to find a previous conversation, recover what was discussed or decided earlier, locate which session touched a topic, resume context from history, or export an old transcript. Trigger keywords - find session, past conversation, previous session, search history, what did we discuss, recover chat, extract transcript.
---

# Session Search

Locate and recover past Claude Code sessions. Every project gets a directory
under `$HOME/.claude/projects/`, and every session is an append-only JSONL
transcript inside it. All listing, searching, and extraction goes through
`scripts/search.py`, which streams transcripts line-by-line and parses each
JSON record so the query only matches real user/assistant text — never
base64 blobs, tool payloads, or progress noise. Transcripts can be multi-GB
and must NEVER be read directly into context.

## Key facts

- Transcript path: `$HOME/.claude/projects/<encoded-path>/<uuid>.jsonl`.
  The encoded path is the project's absolute path with every
  non-alphanumeric character replaced by `-`: `/home/user/Skills` becomes
  `-home-user-Skills`. To map the current cwd to its sessions, apply that
  encoding yourself or just pass the real path via `--project` — the script
  encodes it for you.
- In sandboxes `$HOME` may be `/root`; the script honors `CLAUDE_CONFIG_DIR`
  when set and falls back to `$HOME/.claude`.
- Sessions older than `cleanupPeriodDays` (default 30) are auto-deleted at
  startup; if a session cannot be found, it may have been swept.
- A transcript is a tree: records link via `parentUuid`, and rewinds/retries
  create branches. A conversation is the path from a leaf to the root;
  extraction follows the path ending at the most recently appended leaf and
  notes how many abandoned branches were suppressed.

## When invoked:

1. If the user does not know which project, start with an inventory:
   `python3 scripts/search.py --list-projects`
2. To find sessions by content, pick 1-3 distinctive keywords from the
   user's description and run (relative to this skill's directory):
   `python3 scripts/search.py "keyword" --project /path/to/project --since 2026-05-01`
   Try alternate phrasings if the first query misses; drop `--project` to
   sweep every project.
3. Show the user the matching sessions (uuid, project, timestamp, snippet)
   and confirm which one they mean if more than one matches.
4. To recover the conversation:
   `python3 scripts/search.py --extract UUID --format md --out /tmp/session.md`
   Then read /tmp/session.md if needed — it contains only rendered text with
   tool calls collapsed to one-liners, so it is safe to bring into context
   in normal cases; check its size with `ls -lh` first and read selectively
   if it is large.
5. RUN the script; never read its source or reimplement the logic, and never
   open raw `.jsonl` transcripts with Read/cat/grep.

## Script flags

`python3 scripts/search.py [QUERY] [flags]`

- `QUERY` — case-insensitive text matched only against user and assistant
  message text blocks (meta lines and tool payloads are excluded). Up to 3
  hits are shown per session.
- `--project PATH` — limit to one project; accepts the real path
  (`/home/user/Skills`) or the encoded dir name (`-home-user-Skills`).
- `--since DATE` / `--until DATE` — restrict by record timestamp
  (`YYYY-MM-DD`).
- `--list-projects` — table of encoded project dirs with session counts,
  total bytes, and oldest/newest session dates.
- `--extract UUID` — render one session by walking the leaf-to-root
  `parentUuid` path: user/assistant text in full, `tool_use`/`tool_result`
  collapsed to one-line summaries, thinking blocks reduced to size markers,
  meta/progress lines skipped, compaction summaries and sidechains labeled.
- `--format md|json` — extraction output format (default `md`).
- `--out FILE` — write extraction to a file instead of stdout (recommended;
  keeps large conversations out of your context until sized).

## Safety rules

- Transcripts are plaintext: search snippets and extracted Markdown may
  contain secrets that tools once read (API keys, tokens, passwords). Warn
  the user before pasting snippets anywhere external, and prefer the
  session-collector skill with `--redact` for anything that leaves the
  machine.
- All operations are strictly read-only against `~/.claude/`; never modify
  or delete session files.
- Never Read/cat/head/grep raw `.jsonl` files into context; only consume the
  script's output.

## Final report format

Report back with:
- The query/filters used and how many hits across how many sessions.
- A short table of candidate sessions: uuid, project, timestamp, snippet.
- If extracted: the output file path, how many records were rendered, and
  whether branches were suppressed (and what that means — rewound/retried
  history not shown).
- A one-line secrets caution if snippets or extracts will be shared.
