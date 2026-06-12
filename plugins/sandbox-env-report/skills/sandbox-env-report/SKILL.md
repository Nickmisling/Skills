---
name: sandbox-env-report
description: Collect a secrets-masked diagnostic snapshot of a Claude Code sandbox or remote execution environment — CLAUDE_CODE_* env vars, proxy settings, OS and tool versions, network reachability probes, and the claude.ai web-session URL. Use when debugging "works locally, fails in sandbox" issues, setup-script or SessionStart hook problems, blocked network/proxy errors, or when filing an environment bug report.
---

# Sandbox Environment Report

Produces a single, shareable diagnostic snapshot of the current Claude Code
execution environment. Sandboxes (Claude Code on the web) differ from local
machines in ways that cause confusing failures: all egress goes through a
security proxy, `$HOME` may be `/root` while the workspace lives under
`/home/user`, containers are ephemeral, and setup scripts behave
differently from the interactive session shell. This skill gathers the
facts needed to diagnose those differences in one pass, with secrets
masked so the output is safe to paste into a bug report.

When invoked:

1. Run the collector (relative to this skill directory):
   `python3 scripts/env_report.py`
   Run the script — do not read it. Add `--json` for machine-readable
   output, or `--no-network` to skip the reachability probes (e.g. when
   the user only wants env/system info, or probes would be noisy).
2. Present the report and interpret it for the user:
   - `CLAUDE_CODE_REMOTE=true` plus `IS_SANDBOX=yes` confirms a web
     sandbox; their absence means a local run.
   - The probe results infer the network policy level: None (everything
     blocked), Trusted (package registries such as npm/PyPI/RubyGems/
     crates.io/proxy.golang.org reachable, the rest blocked), All, or
     Custom. GitHub goes through a separate scoped-credential proxy and
     can be reachable regardless of the network level.
   - The report derives the claude.ai web-session URL from
     `CLAUDE_CODE_REMOTE_SESSION_ID` (`cse_...` maps to
     `https://claude.ai/code/session_...`) — useful for referencing the
     session in reports.
3. If the user is debugging setup scripts, remind them of the known
   pitfalls:
   - Variables from the environment's `.env` field reach the session
     shell but NOT setup scripts. The workaround is a SessionStart hook
     gated on `CLAUDE_CODE_REMOTE`.
   - Setup scripts are cached for about 7 days and are never re-run when
     a session resumes — a changed setup script may not have taken
     effect yet.
   - Containers are ephemeral: any work that must survive the session
     has to be committed and pushed.
4. If something looks anomalous (e.g. `$HOME` differs from the workspace
   root, a registry the user needs is blocked, the diagnostics file shows
   errors), call it out explicitly with the likely fix.

## Background

- Verified sandbox env vars include: `CLAUDE_CODE_REMOTE`,
  `CLAUDE_CODE_REMOTE_SESSION_ID`, `CLAUDE_CODE_SESSION_ID` (local uuid),
  `CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE` (e.g. cloud_default),
  `CLAUDE_CODE_CONTAINER_ID`, `CLAUDE_CODE_ENTRYPOINT`,
  `CLAUDE_CODE_VERSION`, `CLAUDE_CODE_ENVIRONMENT_RUNNER_VERSION`,
  `CLAUDE_CODE_BASE_REF`, `CLAUDE_CODE_ACCOUNT_UUID`,
  `CLAUDE_CODE_ORGANIZATION_UUID`, `CLAUDE_CODE_USER_EMAIL`,
  `CLAUDE_CODE_DIAGNOSTICS_FILE` (a /tmp diagnostics log the script
  tails), `CLAUDE_CODE_PROXY_RESOLVES_HOSTS`, `CLAUDECODE=1`,
  `IS_SANDBOX=yes`, and `AI_AGENT`.
- The script masks account/organization UUIDs, emails, and anything that
  looks like a token or credential, showing only the last 4 characters.
- Network probes are HTTPS HEAD requests with a short timeout to
  github.com, registry.npmjs.org, and pypi.org — enough to classify the
  policy without generating real traffic.

## Safety rules

- Never print unmasked credentials, full account/org UUIDs, or full
  emails; the script handles masking — do not "helpfully" echo raw env
  vars alongside it.
- The output is designed to be safe to share, but always tell the user to
  review it once before posting publicly.
- Do not modify any environment configuration as part of this skill; it
  is strictly read-only diagnostics.

## Report format

Lead with a one-paragraph verdict (sandbox or local, network level,
anomalies found), then the script output, then a short "what this means /
suggested next step" section tailored to the user's problem.
