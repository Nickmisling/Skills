---
name: subagents-mode
description: "Manual invocation only. Invoke this skill ONLY when the user explicitly runs /subagents-mode or explicitly says to enter \"subagents mode.\" Never auto-trigger on any other phrasing."
---

# Subagents Mode

Purpose: keep this session's context window small so it never hits compaction. Every token of tool output that lands in this conversation brings compaction closer. Subagents burn their own context, not this session's — so any work that would pull bulk content into this session gets delegated, and only a short report comes back.

## Core rule

You do not perform tool work yourself; you orchestrate. Any work whose tool output would land in this context — reading files, searching, running commands, editing code, fetching web content — goes to a subagent, which does it in its own context window and returns only a concise final report.

Exception: if a request is answerable from conversation context or general knowledge with no tool calls at all (a follow-up question, a clarification, "thanks"), answer it directly. Spawning an agent for a no-tool answer wastes more context than it saves.

## Tools you may still call yourself

Only these, and only for orchestration: `Agent`, `SendMessage`, `TaskCreate`, `TaskList`, `TaskGet`, `TaskUpdate`, `TaskOutput`, `TaskStop`, `AskUserQuestion`, `Skill` (when the user explicitly invokes one), and `ToolSearch` (some of the tools above are deferred — load their schemas with ToolSearch; this is always permitted).

Every other tool (`Read`, `Write`, `Edit`, `Bash`, `Grep`, `Glob`, `WebFetch`, `WebSearch`, `NotebookEdit`, etc.) is forbidden to you. If a job needs one of them, a subagent runs it — not you.

## Report discipline — this is what makes the mode work

A subagent that dumps its findings back into this session defeats the purpose. In **every** `Agent` prompt you write:

- Set an explicit report budget: "Reply with at most ~200 words: conclusions, decisions made, and `file:line` references only. Do not paste file contents, diffs, command output, or raw logs unless explicitly asked for them verbatim."
- For follow-up work in an area an agent already covered, `SendMessage` that same agent instead of spawning a new one — it already holds the bulky context; keep the bulk there.
- Trust reports: never re-derive in this session what an agent already reported. If a report is insufficient, ask that agent a narrow follow-up question.
- Batch related units: one agent per coherent area of work beats many agents each returning a separate report.

## For every user request that needs tools

1. Split the request into units of work.
2. **2+ independent units → spawn an agent team**, not separate fire-and-forget subagents:
   - `TaskCreate` one shared task per unit.
   - Call `Agent` once per unit to spawn a teammate; give each a distinct name in the prompt.
   - Instruct each teammate to message other teammates by name (`SendMessage`) about findings/conflicts.
   - Do the task bookkeeping yourself: `TaskUpdate` a unit's task to `in_progress` (owner: the teammate's name) when you spawn its teammate, and to `completed` when that teammate's report arrives. Task tools are typically unavailable inside subagent contexts, so never instruct teammates to claim or update tasks — they can't.
3. **1 indivisible unit → spawn exactly one `Agent`** for it. Still never do it yourself.
4. While agents run, end your turn and act on completion notifications. Never poll, sleep, or start doing their work yourself while waiting.
5. Synthesize the reports into your reply to the user.

## Hard rules

- Never read, write, or run anything directly — always via a spawned agent.
- If you catch yourself about to call a forbidden tool, stop and spawn an `Agent` instead.
- If agent teams are unavailable, fall back to plain `Agent` calls, one per unit, in parallel where units are independent.
- This mode stays active until the user explicitly exits it (e.g. "exit subagents mode" or `/subagents-mode off`). At the start of each turn, restate to yourself that subagents mode is active so the mode survives long sessions and context summarization.
