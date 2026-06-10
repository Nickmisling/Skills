# Skills

A collection of **utility skills** for [Claude Code](https://code.claude.com/docs) —
focused on testing, scaffolding, and authoring other Agent Skills. This
repository is a **plugin marketplace**: add it once and install any skill it
hosts.

## Add the marketplace

```shell
/plugin marketplace add Nickmisling/Skills
```

Then install a plugin from it:

```shell
/plugin install create-skill@skills
```

To pull in new or updated plugins later:

```shell
/plugin marketplace update skills
```

You can also add it non-interactively from your terminal:

```bash
claude plugin marketplace add Nickmisling/Skills
claude plugin install create-skill@skills
```

## What's inside

| Plugin            | Category  | Description                                                       |
| ----------------- | --------- | ----------------------------------------------------------------- |
| `create-skill`    | authoring | Scaffold a new skill plugin and register it in the marketplace.   |
| `validate-skills` | testing   | Validate the marketplace catalog and every plugin manifest.       |
| `hello-world`     | testing   | Minimal skill for smoke-testing that install and invocation work. |

## Repository layout

```
.
├── .claude-plugin/
│   └── marketplace.json          # marketplace catalog (lists every plugin)
└── plugins/
    └── <plugin-name>/            # one plugin per directory
        ├── .claude-plugin/
        │   └── plugin.json       # plugin manifest
        └── skills/
            └── <skill-name>/
                └── SKILL.md      # the skill itself
```

## Add a new skill

The fastest way is to install and use the `create-skill` plugin, which
scaffolds and registers a new skill for you. To do it by hand:

1. Create `plugins/<name>/.claude-plugin/plugin.json` with `name`,
   `description`, and `version`.
2. Create `plugins/<name>/skills/<name>/SKILL.md` with YAML frontmatter
   (`name`, `description`) and step-by-step instructions.
3. Add a matching entry to the `plugins` array in
   `.claude-plugin/marketplace.json` (`name`, `source`, `description`).
4. Add a row to the table above.
5. Validate:

   ```bash
   claude plugin validate .
   ```

Bump the `version` field on each plugin whenever you ship changes so existing
users receive the update. See the
[plugin marketplace docs](https://code.claude.com/docs/en/plugin-marketplaces)
for the full schema and hosting options.

## License

[MIT](./LICENSE)
