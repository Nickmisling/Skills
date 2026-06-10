# Skills

A collection of **utility skills** for [Claude Code](https://code.claude.com/docs) —
focused on testing, scaffolding, and authoring other Agent Skills. This
repository is a **plugin marketplace**: add it once and install any skill it
hosts.

> No skills are published yet. The marketplace is set up and ready — add your
> first skill following the steps below.

## Add the marketplace

```shell
/plugin marketplace add Nickmisling/Skills
```

Then install a plugin from it (once skills exist):

```shell
/plugin install <plugin-name>@skills
```

To pull in new or updated plugins later:

```shell
/plugin marketplace update skills
```

You can also add it non-interactively from your terminal:

```bash
claude plugin marketplace add Nickmisling/Skills
```

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

1. Create `plugins/<name>/.claude-plugin/plugin.json` with `name`,
   `description`, and `version`.
2. Create `plugins/<name>/skills/<name>/SKILL.md` with YAML frontmatter
   (`name`, `description`) and step-by-step instructions.
3. Add a matching entry to the `plugins` array in
   `.claude-plugin/marketplace.json` (`name`, `source`, `description`).
4. Validate:

   ```bash
   claude plugin validate .
   ```

Bump the `version` field on each plugin whenever you ship changes so existing
users receive the update. See the
[plugin marketplace docs](https://code.claude.com/docs/en/plugin-marketplaces)
for the full schema and hosting options.

## License

[MIT](./LICENSE)
