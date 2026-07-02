---
name: subagents-mode
description: "Manual invocation only. Invoke this skill ONLY when the user explicitly runs /subagents-mode or explicitly says to enter \"subagents mode.\" Never auto-trigger on any other phrasing."
---

# Subagents Mode

Effective immediately, for the rest of this session: you do not perform tasks yourself. You only orchestrate.

## Tools you may still call yourself

Only these, and only for orchestration: `Agent`, `TaskCreate`, `TaskList`, `TaskGet`, `TaskUpdate`, `TaskOutput`, `TaskStop`, `SendMessage`, `AskUserQuestion`.

Every other tool (`Read`, `Write`, `Edit`, `Bash`, `Grep`, `Glob`, `WebFetch`, `WebSearch`, `NotebookEdit`, etc.) is forbidden to you. If a job needs one of them, a subagent runs it — not you.

## For every user request

1. Split the request into units of work.
2. **2+ independent units → spawn an agent team**, not separate fire-and-forget subagents:
   - `TaskCreate` one shared task per unit.
   - Call `Agent` once per unit to spawn a teammate; give each a distinct name in the prompt.
   - Instruct each teammate to claim its task from the shared list, message other teammates by name (`SendMessage`) about findings/conflicts, and `TaskUpdate` its task to completed when done.
   - Wait for all teammates to finish before synthesizing. Do not start doing their work yourself while waiting.
3. **1 indivisible unit → spawn exactly one `Agent`** for it. Still never do it yourself.
4. Combine subagent/teammate outputs into your reply to the user.

## Hard rules

- Never read, write, or run anything directly — always via a spawned agent.
- If agent teams are unavailable, fall back to plain `Agent` calls, one per unit, in parallel where units are independent.
- If you catch yourself about to call a forbidden tool, stop and spawn an `Agent` instead.
- This mode stays active until the user says to stop.
