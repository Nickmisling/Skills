# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A collection of Claude Code Skills — each skill is a directory containing a `SKILL.md` that packages instructions Claude Code loads on demand (via the `Skill` tool / `/<skill-name>` slash command). There is no build, lint, or test tooling; the repository's only content is skill definitions in Markdown.

## Repository structure

Each skill lives in its own top-level directory named after the skill, containing at minimum a `SKILL.md`:

```
<skill-name>/SKILL.md
```

`SKILL.md` starts with YAML frontmatter (`name`, `description`) followed by the skill's instructions in Markdown. The `description` field controls when/how the skill is triggered — read it carefully, since it often encodes strict triggering rules (e.g. "manual invocation only," specific trigger phrases to match or avoid).

## Adding or editing a skill

- Create a new directory named after the skill; add `SKILL.md` with `name` and `description` frontmatter.
- Write the `description` precisely: it is the only signal Claude Code uses to decide when to auto-trigger (or, for manual-only skills, when to refuse to auto-trigger) the skill. State explicitly whether the skill is manual-only, and list exact invocation phrases if so.
- Keep instructions in the body imperative and unambiguous — this text is injected directly into a future Claude Code session's context to steer its behavior, not documentation for a human reader.
- No code to compile or tests to run — validate a new/edited skill by reading it back and checking the frontmatter is valid YAML and the description matches the intended triggering behavior described in this file.
