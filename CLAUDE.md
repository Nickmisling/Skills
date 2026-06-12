# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Claude Code **plugin marketplace** hosting Agent Skills as installable plugins. Users add the marketplace once (`/plugin marketplace add Nickmisling/Skills`) and then install individual skills from it.

## Adding a new skill

1. Copy `plugins/example-skill` to `plugins/<your-plugin-name>`.
2. Rename `plugins/<your-plugin-name>/skills/example-skill` to match and edit its `SKILL.md`.
3. Update `name`, `description`, and `version` in `plugins/<your-plugin-name>/.claude-plugin/plugin.json`. (Do not add `category` or `keywords` here — they belong only in `marketplace.json` and are ignored in `plugin.json`.)
4. Add a matching entry to `.claude-plugin/marketplace.json` (fields: `name`, `source`, `description`, `version`, `author`, `license`, `category`, `keywords`).
5. Update the plugin table in `README.md`.
6. Validate: `claude plugin validate .`

Bump `version` in both `plugin.json` and `marketplace.json` on every change so installed users receive updates.

## Key files

- `.claude-plugin/marketplace.json` — the catalog; lists every plugin with metadata. This is what Claude Code reads when a user adds the marketplace.
- `plugins/<name>/.claude-plugin/plugin.json` — per-plugin manifest (name, version, author, license). Must stay in sync with the marketplace entry.
- `plugins/<name>/skills/<name>/SKILL.md` — the skill itself: YAML frontmatter (`name`, `description`) + markdown instructions Claude follows when the skill is invoked.
- `.claude/skills/` — project-level skills loaded automatically in sessions on this repo (no install required). Keep these in sync with their counterpart under `plugins/`.

## Validation

```bash
claude plugin validate .
```

No build step, no test suite — the only CI artifact is the JSON schema validation above.
