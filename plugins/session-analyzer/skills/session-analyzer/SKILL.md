---
name: session-analyzer
description: Run statistical analysis on a Claude Code session transcript without loading it into context - token totals, cache-hit ratio, tool-call distribution, record-type byte shares, most expensive turns, rewind/branch points, compactions, and duration. Use when the user asks why a session is slow, large, or expensive, wants token or cost stats, tool usage breakdowns, or a session health check. Trigger keywords - analyze session, token usage, session stats, transcript size, cache hit, expensive turns, context bloat.
---

# Session Analyzer

Produce a statistical profile of a Claude Code session transcript by
streaming it once through `scripts/analyze.py`. Transcripts are append-only
JSONL files that can grow to multiple gigabytes; the script accumulates
counters only, so memory stays flat regardless of file size. Your job is to
run the script and then INTERPRET the numbers for the user — the raw dump is
not the deliverable.

## When invoked:

1. Locate the transcript. Sessions live at
   `$HOME/.claude/projects/<encoded-path>/<session-uuid>.jsonl`, where the
   encoded path is the project's absolute path with every non-alphanumeric
   character replaced by `-` (`/home/user/Skills` becomes
   `-home-user-Skills`). In sandboxes `$HOME` may be `/root`; honor
   `CLAUDE_CONFIG_DIR` if set. For the live session, the UUID is in
   `CLAUDE_CODE_SESSION_ID`. If no UUID is given, pick the newest:
   `ls -t "$HOME/.claude/projects/<encoded>/"*.jsonl | head -1`.
2. RUN the script (never read or reimplement it):
   `python3 scripts/analyze.py /path/to/SESSION.jsonl --top 5`
   (path relative to this skill's directory, or absolute).
3. Read the script's stdout — that is the only representation of the
   transcript you should ever have in context.
4. Interpret the results (see guide below) and report.

## Script flags

`python3 scripts/analyze.py FILE [--json] [--top N]`

- `FILE` — path to the session `.jsonl` transcript (required).
- `--json` — machine-readable JSON output; use when you need to compare
  several sessions or feed numbers into further computation.
- `--top N` — number of most-expensive turns to list, by output tokens and
  by tool-result bytes (default 5).

## What the script reports

Total lines/bytes; record-type histogram with per-type byte share; message
counts by role; token totals from `message.usage` (input, output,
cache-create, cache-read) and the cache-hit ratio; tool-call distribution by
tool name with counts and total result bytes; top-N turns by output tokens
and by result bytes; sidechain (subagent) line count; compaction events
(`isCompactSummary`) with timestamps; session duration from first/last
timestamps; branch points (uuids with multiple children in the `parentUuid`
tree — evidence of rewind/retry); Claude Code versions seen.

## Interpretation guide

- Cache-hit ratio: above roughly 80% is healthy (cache reads are billed at a
  small fraction of fresh input tokens); a low ratio in a long session
  suggests cache-busting churn, e.g. frequently changing system context.
- A progress/meta record type holding more than ~50% of bytes indicates
  transcript bloat from streaming/progress events, not real conversation.
- Large tool-result bytes for one tool (often Bash or Read) usually explains
  a fat transcript; suggest narrower reads or output filtering.
- Many branch points mean the user rewound or retried often — only the path
  from the latest leaf to the root is the "live" conversation.
- Compaction events mark where context was summarized; frequent compactions
  in a short span indicate the session was running at the context ceiling.
- Sidechain lines belong to subagents; full subagent transcripts live in the
  sibling directory `<uuid>/subagents/`.

## Safety rules

- NEVER Read, cat, head, tail, or grep the `.jsonl` transcript into context.
  Transcripts can be multi-GB and contain plaintext secrets. ALL access goes
  through `scripts/analyze.py`. `ls -lh` for file size is the only direct
  inspection allowed.
- The script is strictly read-only; never modify files under `~/.claude/`.
- Quote uuids/timestamps from script output when citing expensive turns; do
  not attempt to open those turns in the raw file.

## Final report format

Report back with:
- One-line session summary: file, size, duration, line count.
- Token economics: input/output totals, cache-hit ratio, and a plain-English
  verdict (good/poor and why).
- Top cost drivers: heaviest record types by byte share and heaviest tools
  by result bytes, with the top expensive turns.
- Structure notes: branch points, compactions, sidechain activity — and what
  each implies, per the interpretation guide.
- One or two concrete recommendations if anything looks unhealthy.
