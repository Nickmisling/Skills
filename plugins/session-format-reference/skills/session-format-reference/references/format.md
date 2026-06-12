# Claude Code Session JSONL Format — Full Reference

Scope: the transcript files under `~/.claude/projects/` and their sibling
artifacts. One JSON object per line, append-only, UTF-8. The format drifts
across Claude Code versions; every line carries a `version` field naming
the Claude Code version that wrote it. Robust tooling checks `version` per
line and treats unknown types and fields as expected.

## 1. File layout

```
~/.claude/
  projects/
    <encoded-path>/                # '/' replaced by '-':
                                   # /home/user/Skills -> -home-user-Skills
      <session-uuid>.jsonl         # main transcript
      <session-uuid>/              # sibling artifact dir (may be absent)
        subagents/                 # sidechain transcripts (Task/Agent runs)
        tool-results/              # spill files for large tool outputs
  file-history/<session-uuid>/     # pre-edit snapshots (not transcript data)
  history.jsonl                    # global prompt history
```

- Session filenames are UUIDs; the same UUID appears as `sessionId` inside
  every line of the file.
- Subagent transcripts in `subagents/` use the same line format but with
  `isSidechain: true`.
- A `<uuid>/` dir without a matching `<uuid>.jsonl` is an orphan (the
  transcript was cleaned but the artifacts were not).

## 2. Record types

| `type`                   | Meaning |
|--------------------------|---------|
| `user`                   | A user turn OR a tool-result carrier (tool results come back as user-role messages). |
| `assistant`              | A model turn: text, thinking, and/or tool_use blocks; carries `message.usage` and model id. |
| `system`                 | Harness-injected system events/notices. |
| `summary`                | Compaction/summary record: `{type, summary, leafUuid}` pointing at the leaf it summarizes. |
| `attachment`             | Attached content (pastes, images) referenced by a turn. |
| `queue-operation`        | Queued-message bookkeeping. |
| `file-history-snapshot`  | Marker tying a pre-edit snapshot to the timeline. |
| progress / compaction / hook meta events | Operational events; names drift across versions — do not enumerate exhaustively, skip unknowns. |

## 3. Top-level fields

| Field | Type | Meaning |
|-------|------|---------|
| `type` | string | Record type (table above). Only field safe to assume on every line, along with `uuid` on event lines. |
| `uuid` | string | Unique id of this record. |
| `parentUuid` | string or null | Parent record; `null` on roots. Lines form a TREE: rewind/retry creates branches. A conversation = the path from a leaf to the root, NOT the file order. |
| `sessionId` | string | Session UUID; matches the filename. |
| `timestamp` | string | ISO 8601 wall-clock time. |
| `version` | string | Claude Code version that wrote this line. Check per line. |
| `isSidechain` | bool | `true` in subagent transcripts under `subagents/`. |
| `userType` | string | e.g. `"external"` for real user input. |
| `cwd` | string | Working directory at the time of the record. |
| `gitBranch` | string | Git branch at the time of the record. |
| `entrypoint` | string | How the session was started, e.g. `remote_mobile`. |
| `promptId` | string | Groups records belonging to one user prompt. |
| `requestId` | string | API request id for the assistant turn. |
| `isMeta` | bool | Harness-internal record, not real conversation content. |
| `isCompactSummary` | bool | Record produced by context compaction. |
| `leafUuid` | string | On `summary` records: the leaf line being summarized. |
| `message` | object | The API-shaped message (section 4). On `user`/`assistant` lines. |
| `toolUseResult` | any | On user-type lines that carry a tool result: structured RAW tool output (richer than the rendered `tool_result` block). Shape varies by tool. |
| `summary` | string | On `summary` records: the summary text. |

## 4. `message` object

```jsonc
{
  "role": "user" | "assistant",
  "model": "claude-...",          // assistant lines
  "content": "plain string"        // or an array of blocks:
  // { "type": "text",     "text": "..." }
  // { "type": "thinking", "thinking": "..." }
  // { "type": "tool_use", "id": "toolu_...", "name": "Bash", "input": {...} }
  // { "type": "tool_result", "tool_use_id": "toolu_...",
  //   "content": "..." | [blocks], "is_error": true? }
  ,
  "usage": {                       // assistant lines
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0
  }
}
```

Notes:

- `content` may be a bare string (early/simple turns) or a block array —
  handle both: `(.message.content | if type == "string" then ... )`.
- Tool results arrive as the NEXT user-type line containing a
  `tool_result` block whose `tool_use_id` matches the assistant's
  `tool_use` block `id`. Join on those ids, not on adjacency.
- The same user line often also carries top-level `toolUseResult` with the
  structured output (e.g. for file reads: file path, line counts; for
  Bash: stdout/stderr/exit code).
- Large tool outputs may be truncated inline and spilled to files under
  the sibling `tool-results/` directory; a short inline block does not
  imply a short output.

## 5. Special records

- **Summary**: `{"type":"summary","summary":"<title/summary text>",
  "leafUuid":"<uuid>"}`. Written at compaction and for the session list
  UI. May appear at the top of the file or interleaved. To find what a
  summary covers, walk `leafUuid` -> `parentUuid` chain to the root.
- **Slash commands**: appear inside user `text` content as
  command markup, with a command-name element and a command-args element
  (literally tags in the text). Local command output appears in a
  local-command-stdout element. Match them textually; they are not
  separate record types.
- **Sidechains**: each Task/Agent subagent run writes its own transcript
  under `<session>/subagents/`, same format, `isSidechain: true`. Token
  accounting that only reads the main file undercounts.

## 6. Path encoding

`projects/` dir names encode the project cwd by replacing every `/` with
`-`. `/home/user/Skills` -> `-home-user-Skills` (leading `-` from the
leading `/`). The encoding is lossy (`-` vs `/` ambiguity for paths
containing hyphens) — when reversing, prefer the `cwd` field inside the
transcript lines over decoding the directory name.

## 7. Version drift checklist

- Check the per-line `version` field; one file can span upgrades.
- Unknown `type` values: skip, do not error.
- Unknown/missing fields: use `// default` in jq, `.get()` in Python.
- Do not assume `message` exists on every line (`summary`, meta events
  lack it).
- Do not assume content is an array (may be a string).

## 8. Worked jq examples

Always stream — never load a multi-MB transcript into agent context.

```bash
S=~/.claude/projects/-home-user-Skills/<uuid>.jsonl

# Total output tokens for a session
jq -s 'map(.message.usage.output_tokens // 0) | add' "$S"

# Full token accounting (input/output/cache)
jq -s '
  { in:   map(.message.usage.input_tokens // 0) | add,
    out:  map(.message.usage.output_tokens // 0) | add,
    c_w:  map(.message.usage.cache_creation_input_tokens // 0) | add,
    c_r:  map(.message.usage.cache_read_input_tokens // 0) | add }' "$S"

# Record-type histogram
jq -r .type "$S" | sort | uniq -c | sort -rn

# Tool-call histogram
jq -r '.message.content[]? | select(.type=="tool_use") | .name' "$S" \
  | sort | uniq -c | sort -rn

# First user prompt (handles string and block content)
jq -r 'select(.type=="user" and (.isMeta != true))
       | .message.content
       | if type=="string" then . else (map(.text // empty) | join("\n")) end' \
  "$S" | head -5

# Leaves of the tree (records nobody points at) — branch/rewind detection
jq -sr '[.[].parentUuid] as $parents
        | .[] | select(.uuid as $u | $parents | index($u) | not) | .uuid' "$S"

# Find sessions by content across all projects (filenames only)
grep -l "needle" ~/.claude/projects/*/*.jsonl

# Sessions sorted by size before reading anything
du -h ~/.claude/projects/*/*.jsonl | sort -rh | head

# Per-line versions present in a file (drift check)
jq -r '.version // "unknown"' "$S" | sort -u
```

## 9. Sensitivity

Transcripts are plaintext. Tool outputs routinely contain environment
dumps, tokens, and file contents — secrets land in them. Treat transcript
content as sensitive: review before sharing, and never paste raw lines
into public bug reports.
