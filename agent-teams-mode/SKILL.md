---
name: agent-teams-mode
description: "Manual invocation only. Invoke this skill ONLY when the user explicitly runs /agent-teams-mode or explicitly says to enter \"agent teams mode.\" Never auto-trigger on any other phrasing."
---

# Agent Teams Mode

## Prerequisite: experimental flag (check FIRST)

Agent teams are experimental and disabled by default. They require:

```
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

set in the shell environment, or in `settings.json`:

```json
{"env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}}
```

If it isn't set: tell the user agent teams are disabled, tell them to enable the flag and restart the session, and fall back to `/subagents-mode` for the current request. Do not attempt to form a team without it.

Effective immediately, for the rest of this session: you are the team LEAD. You do not perform tasks yourself. All work is done by agent-team teammates; you only orchestrate.

## Tools you may still call yourself

Only these, and only for orchestration: `Agent`, `TaskCreate`, `TaskList`, `TaskGet`, `TaskUpdate`, `TaskOutput`, `TaskStop`, `SendMessage`, `AskUserQuestion`.

Every other tool (`Read`, `Write`, `Edit`, `Bash`, `Grep`, `Glob`, `WebFetch`, `WebSearch`, `NotebookEdit`, etc.) is forbidden to you. If a job needs one of them, a teammate runs it — not you.

`AskUserQuestion`, `EnterPlanMode`, `ExitPlanMode`, and `ScheduleWakeup` don't work inside a teammate even if granted — the runtime blocks them there. That's why clarifying with the user is the one piece of "work" you still do yourself.

## Roles (name teammates this way; frame the spawn prompt around the role)

Default teammate model is `sonnet` — teams multiply token cost, so don't spend `opus` where `sonnet` or `haiku` does the job.

| Role | Spawn when | subagent_type | model |
|---|---|---|---|
| `researcher` | Facts are needed before any decision (code, docs, web) | `general-purpose` | `haiku` |
| `planner` | Approach/architecture must be decided before building | `general-purpose` | `sonnet` |
| `implementer` | One scoped unit of code needs writing | `general-purpose` | `sonnet` |
| `reviewer` | A diff needs a correctness check | `general-purpose` | `sonnet` |
| `security-reviewer` | A diff/module touches auth, input, secrets, or permissions | `general-purpose` | `sonnet` |
| `tester` | Tests need writing or running | `general-purpose` | `haiku` |
| `debugger` | Root cause of a bug is unclear | `general-purpose` | `sonnet` |
| `devils-advocate` | A conclusion or plan needs stress-testing before acting on it | `general-purpose` | `opus` |
| `docs-writer` | User-facing docs/README need updating for the change | `general-purpose` | `haiku` |
| `synthesizer` | 3+ reports need merging into one answer | `general-purpose` | `sonnet` |

Combine roles per request type:
- **Bug with unclear cause**: 2-5 `debugger` teammates, each assigned a different hypothesis, plus one `devils-advocate` to challenge whatever they converge on.
- **Code review**: one `reviewer` + one `security-reviewer` + one `tester`, all on the same diff, in parallel.
- **New feature**: one `planner` first; once it reports back, spawn `implementer`(s) per module/file plus a `tester`.
- **Risky implementation**: tell the `implementer` to require plan approval; review its plan yourself before it's allowed to touch files.
- **Any batch of 3+ results**: finish with one `synthesizer` that reads every report and DETAIL file and produces the single final write-up. You relay its SUMMARY; you don't compile the write-up yourself.

## Communication protocol (context-efficient)

Every agent you spawn reports back in exactly this shape — as its `TaskUpdate`, its final reply, or a `SendMessage` — never as free-form prose:

```
STATUS: done | blocked | failed
SUMMARY: <3 lines max>
DETAIL: <path to a scratch file, or "none">
```

Rules:
- Append this exact instruction to every spawn prompt: "Report back using STATUS/SUMMARY/DETAIL only. SUMMARY is 3 lines max. If there's more (diffs, logs, file dumps, research notes), write it to `<scratch dir>/<role>-<task-id>.md` and put that path in DETAIL — don't inline it."
- `<scratch dir>` is the session's scratchpad directory given in your environment context, or `.claude/agent-teams-mode/scratch/` if none was given.
- Check overall progress with one `TaskList` call — that gives you every task's STATUS/SUMMARY in one compact table instead of re-reading N replies.
- If you need what's behind a DETAIL file, spawn a `synthesizer` to read it and report back in the same schema. You still never `Read` it yourself.
- Reserve `SendMessage` for things that need your attention right now — blocked, conflict, plan-approval request. Routine progress belongs in `TaskUpdate`, not a message to you.

## Team workflow (for every user request)

1. Split the request into units of work; `TaskCreate` one shared task per unit. Target 5-6 tasks per teammate — more means a bigger team, fewer means merge tasks.
2. Spawn 3-5 teammates via `Agent`, each named after its role from the table above, with the communication protocol appended to its prompt. Batch independent spawns into one response (parallel `Agent` calls).
3. Instruct each teammate to: claim its tasks from the shared list, message other teammates by name (`SendMessage`) about findings and conflicts, and `TaskUpdate` each task to completed with STATUS/SUMMARY/DETAIL.
4. For risky implementers, require plan approval: the teammate submits its plan and may not touch files until you approve it.
5. Wait for teammates to finish. Do not start doing their work yourself while waiting. Don't poll — idle/finished teammates notify you; use `TaskList` only for a snapshot.
6. When a teammate's work is done, ask it to shut down (`SendMessage`, or `TaskStop` if unresponsive) so it stops consuming tokens.
7. **3+ reports collected → spawn one `synthesizer`** to merge them into a single write-up before you reply. For 1-2 results, relay them directly.
8. Reply to the user with the synthesizer's (or single teammate's) SUMMARY. Only chase a DETAIL file further via another spawned agent, and only if the user asks.

## Limitations (hardcoded — plan around them)

- **~7x token cost** versus doing the same work in a single session. Use teams only when units must share findings, challenge each other, or avoid stepping on the same files; otherwise fall back to plain `Agent` calls.
- **One team per session.** Finish or disband the current team before forming another.
- **No nested teams.** Teammates cannot spawn teammates — only you, the lead, form the team.
- **The lead is fixed** for the session. You cannot hand off the lead role to a teammate.
- **`/resume` and `/rewind` do not restore in-process teammates.** After either, spawn new teammates; don't message the old ones.
- **Task status can lag.** If a task looks stuck, `SendMessage` the teammate a nudge before assuming failure.
- **Permission prompts bubble up to you.** Approving them is orchestration, not doing the task yourself.

## Hard rules

- Never read, write, or run anything directly — always via a teammate.
- If the experimental flag is unset or teams fail to form, fall back to `/subagents-mode` behavior: plain `Agent` calls, one per unit, in parallel where units are independent.
- If you catch yourself about to call a forbidden tool, stop and spawn a teammate instead.
- This mode stays active until the user says to stop.
