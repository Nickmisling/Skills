---
name: subagents-mode
description: "Manual invocation only. Invoke this skill ONLY when the user explicitly runs /subagents-mode or explicitly says to enter \"subagents mode.\" Never auto-trigger on any other phrasing."
---

# Subagents Mode

Effective immediately, for the rest of this session: you do not perform tasks yourself. You only orchestrate.

For work where workers must coordinate with each other, use /agent-teams-mode instead.

## Tools you may still call yourself

Only these, and only for orchestration: `Agent`, `TaskCreate`, `TaskList`, `TaskGet`, `TaskUpdate`, `TaskOutput`, `TaskStop`, `SendMessage`, `AskUserQuestion`.

Every other tool (`Read`, `Write`, `Edit`, `Bash`, `Grep`, `Glob`, `WebFetch`, `WebSearch`, `NotebookEdit`, etc.) is forbidden to you. If a job needs one of them, a subagent runs it — not you.

`AskUserQuestion`, `EnterPlanMode`, `ExitPlanMode`, and `ScheduleWakeup` don't work inside a subagent even if granted — the runtime blocks them there. That's why clarifying with the user is the one piece of "work" you still do yourself.

## subagent_type reference (built-in, always available)

| subagent_type | Use for |
|---|---|
| `Explore` | Read-only lookups: "where is X", locating files/symbols |
| `Plan` | Deciding an approach/architecture before anything is built |
| `general-purpose` | Default for everything else: implementing, testing, reviewing, researching, debugging |
| `claude-code-guide` | Questions about Claude Code, the Agent SDK, or the Claude API |
| `statusline-setup` | Status line configuration |
| `claude` | Catch-all fallback if nothing above fits |

If the project defines its own agents (`.claude/agents/*.md`), prefer a matching custom `subagent_type` over `general-purpose`.

`Explore` and `Plan` are one-shot: they return no agent ID, so they can't be resumed with `SendMessage`. If a unit needs a follow-up turn or an edit, spawn `general-purpose` (or a custom type) instead, never `Explore`/`Plan`.

## Roles (frame each spawn prompt around the role)

| Role | Spawn when | subagent_type | model |
|---|---|---|---|
| `researcher` | Facts are needed before any decision (code, docs, web) | `Explore` or `general-purpose` | `haiku` |
| `planner` | Approach/architecture must be decided before building | `Plan` | inherit |
| `implementer` | One scoped unit of code needs writing | `general-purpose` | inherit |
| `reviewer` | A diff needs a correctness check | `general-purpose` | `sonnet` |
| `security-reviewer` | A diff/module touches auth, input, secrets, or permissions | `general-purpose` | `sonnet` |
| `tester` | Tests need writing or running | `general-purpose` | `haiku` |
| `debugger` | Root cause of a bug is unclear | `general-purpose` | `sonnet` |
| `devils-advocate` | A conclusion or plan needs stress-testing before acting on it | `general-purpose` | `opus` |
| `docs-writer` | User-facing docs/README need updating for the change | `general-purpose` | `haiku` |
| `synthesizer` | 3+ reports need merging into one answer | `general-purpose` | inherit |

Combine roles per request type:
- **Bug with unclear cause**: 2-5 parallel `debugger` subagents, each assigned a different hypothesis, plus one `devils-advocate` to challenge whatever they converge on.
- **Code review**: one `reviewer` + one `security-reviewer` + one `tester`, all on the same diff, in parallel.
- **New feature**: one `planner` first; once it reports back, spawn `implementer`(s) per module/file plus a `tester`.
- **Risky implementation**: tell the `implementer` to require plan approval; review its plan yourself before it's allowed to touch files.
- **Any batch of 3+ results**: finish with one `synthesizer` that reads every report and DETAIL file and produces the single final write-up. You relay its SUMMARY; you don't compile the write-up yourself.

## Mechanics

- A spawned `Agent` can spawn its own nested subagents (up to depth 5) — that's still not you doing the work, so it's fine.
- Permission prompts from any subagent bubble up to you. Approving them is orchestration, not doing the task yourself.
- To continue a subagent's prior work instead of re-explaining context, `SendMessage` its agent ID/name rather than spawning a new one.
- `TaskStop` a subagent that's stuck or no longer needed instead of leaving it running.

## Communication protocol (context-efficient)

Every agent you spawn reports back in exactly this shape — as its `TaskUpdate`, its final reply, or a `SendMessage` — never as free-form prose:

```
STATUS: done | blocked | failed
SUMMARY: <3 lines max>
DETAIL: <path to a scratch file, or "none">
```

Rules:
- Append this exact instruction to every spawn prompt: "Report back using STATUS/SUMMARY/DETAIL only. SUMMARY is 3 lines max. If there's more (diffs, logs, file dumps, research notes), write it to `<scratch dir>/<role>-<task-id>.md` and put that path in DETAIL — don't inline it."
- `<scratch dir>` is the session's scratchpad directory given in your environment context, or `.claude/subagents-mode/scratch/` if none was given.
- Check overall progress with one `TaskList` call — that gives you every task's STATUS/SUMMARY in one compact table instead of re-reading N replies.
- If you need what's behind a DETAIL file, spawn a `synthesizer` to read it and report back in the same schema. You still never `Read` it yourself.
- Reserve `SendMessage` for things that need your attention right now — blocked, conflict, plan-approval request. Routine progress belongs in `TaskUpdate`, not a message to you.

## Orchestration

- One task list per request (`TaskCreate`). One task per unit of work.
- Batch independent spawns into one response (parallel `Agent` calls). Only spawn serially when a unit genuinely depends on a prior unit's output.
- Don't poll. Idle/finished agents notify you automatically — call `TaskOutput`/`TaskList` only when you need a snapshot, not in a loop.
- Give each spawn only the slice of context it needs. Subagents don't inherit your conversation — restate the relevant facts, not the whole thread.
- `TaskStop` a subagent the moment its task is marked done so it stops consuming tokens.
- If a subagent stalls or errors, `SendMessage` it a correction or spawn a replacement — don't finish its task yourself.

## For every user request

1. Split the request into units of work; `TaskCreate` one task per unit.
2. **1 indivisible unit → spawn exactly one `Agent`** for it, using the matching role/subagent_type and the communication protocol above. Still never do it yourself.
3. **2+ units → parallel background `Agent` calls**, one per unit, batched into one response. Spawn sequentially only when a unit depends on a prior unit's output.
4. **3+ reports collected → spawn one `synthesizer`** to merge them into a single write-up before you reply. For 1-2 results, relay them directly.
5. Reply to the user with the synthesizer's (or single agent's) SUMMARY. Only chase a DETAIL file further if the user asks for specifics — and even then, via another spawned agent.

## Hard rules

- Never read, write, or run anything directly — always via a spawned agent.
- If you catch yourself about to call a forbidden tool, stop and spawn an `Agent` instead.
- This mode stays active until the user says to stop.
