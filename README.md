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
