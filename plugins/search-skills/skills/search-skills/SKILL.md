---
name: search-skills
description: Search for existing Agent Skills across public skill repositories and marketplaces, then present the matches with descriptions, source links, and install instructions. Use when the user wants to find, discover, look up, or reuse an existing skill for a task instead of writing one from scratch.
---

# Search Skills

Find existing Agent Skills that match what the user needs, gathered from across
the many public skill repositories and marketplaces, and present them with
enough detail to evaluate and install.

## 1. Clarify the need

From the user's request, identify:

- **Capability** — what the skill should do (e.g. "convert PDFs to markdown",
  "review Terraform", "generate commit messages").
- **Keywords** — 2-4 search terms, including synonyms and the tooling involved.

If the request is too vague to search well (e.g. "find me a good skill"), ask
one focused question before searching.

## 2. Search the sources

Cast a wide net. Use whatever search tools are available, in roughly this
order, and combine the results:

1. **A dedicated skills-search tool, if present.** If an MCP tool for searching
   agent skills is available in this session (for example a `search_agent_skills`
   tool), use it first — it is purpose-built and most accurate.

2. **GitHub code search** for skill definition files matching the keywords:
   - `path:SKILL.md <keywords>`
   - `filename:SKILL.md <keywords>`
   - `path:.claude-plugin/marketplace.json <keywords>` to find marketplaces.
   Prefer the GitHub MCP `search_code` tool when available; otherwise use web
   search scoped to `github.com`.

3. **GitHub repository / topic search** for skill collections and marketplaces:
   topics and terms like `claude-skills`, `agent-skills`, `claude-code-plugins`,
   `claude-plugin`, `awesome claude skills`.

4. **Web search** for `"<capability>" claude code skill` or
   `"<capability>" agent skill` to catch marketplaces and blog posts that index
   skills.

5. **Known starting points** — always check Anthropic's official collection at
   `github.com/anthropics/skills`, which is the canonical source for
   first-party skills. Treat any other repo names you don't recognize as
   unverified until you've confirmed they exist via search.

Do not invent repository names or skills. Only report skills you actually found
via a search result or fetched file.

## 3. Confirm and enrich each candidate

For each promising hit, fetch its `SKILL.md` (or the marketplace entry) and read
the YAML frontmatter to get the real `name` and `description`. Discard anything
you can't verify. De-duplicate skills that appear in multiple places, preferring
the most authoritative/maintained source.

## 4. Present the results

Rank by relevance to the request. For each skill, give:

- **Name** and a one-line description of what it does.
- **Source** — the repository or marketplace, with a link.
- **How to get it**, choosing the form that matches the source:
  - Marketplace plugin:
    ```shell
    /plugin marketplace add <owner/repo>
    /plugin install <plugin>@<marketplace>
    ```
  - Standalone `SKILL.md`: note the path and that it can be copied into a
    `skills/<name>/` directory or a plugin in this repository.

Lead with the best 1-3 matches. If nothing matches well, say so plainly and
suggest the closest alternatives or offer to scaffold a new skill instead.

## 5. Offer next steps

Ask whether the user wants you to install a marketplace match, or copy a found
`SKILL.md` into this repository as a new plugin (see the `create-skill` skill if
present, or the "Add a new skill" steps in the repo README).
