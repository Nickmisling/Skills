---
name: validate-skills
description: Validate this marketplace and all of its skill plugins. Use when the user wants to check, validate, lint, or test the skills in the Skills repository before committing or publishing.
---

# Validate Skills

Run Claude Code's plugin validator across the marketplace and every plugin,
then report results.

## Steps

1. Validate the marketplace catalog from the repository root:

   ```bash
   claude plugin validate .
   ```

   This checks `.claude-plugin/marketplace.json` for schema errors, duplicate
   plugin names, source path traversal, and version mismatches.

2. Validate each plugin directory so skill frontmatter is checked too:

   ```bash
   for dir in plugins/*/; do
     echo "== $dir =="
     claude plugin validate "$dir"
   done
   ```

3. Summarize the results: list each plugin and whether it passed, and surface
   any errors or warnings verbatim with the file they came from.

## What to flag

- JSON syntax errors in `marketplace.json` or any `plugin.json`.
- Plugin names that are not kebab-case.
- Sources containing `..` or not starting with `./`.
- Missing `SKILL.md` files or invalid YAML frontmatter.
- A `version` set in both `plugin.json` and the marketplace entry (the
  manifest value wins silently — point this out).

Report a clear pass/fail summary at the end. Do not change files unless the
user asks you to fix what you found.
