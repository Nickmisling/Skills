# Skills

A collection of Agent Skills packaged as installable [Claude Code](https://code.claude.com/docs)
plugins. This repository is a **plugin marketplace** — add it once and install
any skill it hosts.

## Add the marketplace

```shell
/plugin marketplace add Nickmisling/Skills
```

Then install a plugin from it:

```shell
/plugin install example-skill@skills
```

To pull in new or updated plugins later:

```shell
/plugin marketplace update skills
```

You can also add it non-interactively from your terminal:

```bash
claude plugin marketplace add Nickmisling/Skills
claude plugin install example-skill@skills
```

## What's inside

| Plugin          | Description                                                  |
| --------------- | ----------------------------------------------------------- |
| `example-skill` | Starter example skill. Copy it as a template for your own.   |
| `session-doctor` | Read-only diagnosis of Claude Code session and resume problems: JSONL corruption, broken parent chains, orphaned session dirs, oversized transcripts. |
| `session-repair` | Repairs damaged Claude Code session JSONL files so they can be resumed: drops corrupt lines, fixes empty content blocks, strips progress bloat, re-stitches parent chains. Always backs up first. |
| `session-size-guard` | Finds oversized or runaway Claude Code session files before they hang the CLI, shows what is bloating them, and recommends fixes. |
| `history-doctor` | Inspects and repairs Claude Code's prompt history (history.jsonl) and the projects map in ~/.claude.json: malformed lines, stale entries for deleted projects. Safe, backup-first fixes. |
| `session-collector` | Bundle a Claude Code session (transcript, subagents, tool results, file history) into a portable tar.gz archive with optional secret redaction. |
| `session-analyzer` | Statistical analysis of Claude Code session transcripts: token usage, tool-call distribution, cache-hit ratio, expensive turns, branch points, and compaction events. |
| `session-search` | Find past Claude Code sessions across all projects by keyword and date, list projects, and extract any session as readable Markdown or JSON. |
| `workspace-cleaner` | Audit and safely reclaim disk space in ~/.claude: stale transcripts, debug logs, orphaned session artifacts, and legacy directories — dry-run first, opt-in per category. |
| `sandbox-env-report` | Collect a secrets-masked diagnostic snapshot of a Claude Code sandbox/remote environment: env vars, system info, tool versions, network reachability, and the claude.ai session URL. |
| `session-format-reference` | Authoritative reference for the Claude Code session JSONL transcript format and the ~/.claude directory layout, for building session tooling. |

## Repository layout

```
.
├── .claude-plugin/
│   └── marketplace.json          # marketplace catalog (lists every plugin)
└── plugins/
    └── example-skill/            # one plugin per directory
        ├── .claude-plugin/
        │   └── plugin.json       # plugin manifest
        └── skills/
            └── example-skill/
                └── SKILL.md      # the skill itself
```

## Add a new skill

1. Copy `plugins/example-skill` to `plugins/<your-plugin-name>`.
2. Rename the inner `skills/example-skill` directory and edit its `SKILL.md`.
3. Update `name`, `description`, and `version` in the plugin's
   `.claude-plugin/plugin.json`.
4. Add a matching entry to the `plugins` array in
   `.claude-plugin/marketplace.json` (`name`, `source`, `description`).
5. Validate and commit:

   ```bash
   claude plugin validate .
   ```

Bump the `version` field on each plugin whenever you ship changes so existing
users receive the update. See the
[plugin marketplace docs](https://code.claude.com/docs/en/plugin-marketplaces)
for the full schema and hosting options.

## License

[MIT](./LICENSE)
