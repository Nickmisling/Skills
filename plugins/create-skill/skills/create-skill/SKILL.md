---
name: create-skill
description: Scaffold a new skill plugin in this marketplace. Use when the user wants to create, add, generate, or bootstrap a new skill in the Skills repository.
---

# Create Skill

Scaffold a new skill plugin in this repository and register it in the
marketplace catalog.

## Gather inputs

Ask the user for (or infer from their request):

- **name** — kebab-case identifier (lowercase letters, digits, hyphens), e.g. `format-json`.
- **description** — one sentence describing what the skill does and *when* to use it. This is what the model matches on, so make it trigger-oriented.

## Steps

1. Validate the name is kebab-case and not already present under `plugins/`.
2. Create the plugin manifest at
   `plugins/<name>/.claude-plugin/plugin.json`:

   ```json
   {
     "name": "<name>",
     "description": "<description>",
     "version": "0.1.0",
     "author": { "name": "Nickmisling" },
     "license": "MIT"
   }
   ```

3. Create the skill file at `plugins/<name>/skills/<name>/SKILL.md` with YAML
   frontmatter (`name`, `description`) followed by clear, step-by-step
   instructions for what Claude should do when the skill is invoked.
4. Add a matching entry to the `plugins` array in
   `.claude-plugin/marketplace.json`:

   ```json
   {
     "name": "<name>",
     "source": "./plugins/<name>",
     "description": "<description>",
     "version": "0.1.0",
     "author": { "name": "Nickmisling" },
     "license": "MIT",
     "category": "<category>",
     "keywords": ["..."]
   }
   ```

5. Add a row to the plugin table in `README.md`.
6. Validate: run `claude plugin validate .` and
   `claude plugin validate ./plugins/<name>`. Fix any errors before finishing.

## Notes

- The `source` path is relative to the marketplace root and must start with `./`.
- Bump `version` whenever the skill changes so existing users get the update.
- Keep the SKILL.md body focused: state the trigger in the description and the
  procedure in the body.
