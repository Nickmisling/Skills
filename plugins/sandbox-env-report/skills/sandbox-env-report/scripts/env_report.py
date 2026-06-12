#!/usr/bin/env python3
"""Diagnostic snapshot of a Claude Code sandbox/remote execution environment.

Read-only. Collects CLAUDE_CODE_* and proxy env vars (secrets masked),
system info, tool versions, git context, a tail of the diagnostics file,
and quick HTTPS reachability probes to infer the network policy level.
Output is designed to be safe to share, but review before posting.
"""

import argparse
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import urllib.request

ENV_PREFIXES = ("CLAUDE_CODE_",)
ENV_EXACT = ("CLAUDECODE", "IS_SANDBOX", "AI_AGENT")
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY",
              "http_proxy", "https_proxy", "no_proxy", "all_proxy")
SENSITIVE = re.compile(r"(ACCOUNT|ORGANIZATION|EMAIL|TOKEN|SECRET|KEY|"
                       r"PASSWORD|CREDENTIAL|AUTH)", re.IGNORECASE)
PROBES = ["https://github.com", "https://registry.npmjs.org", "https://pypi.org"]


def mask(value: str) -> str:
    """Show only the last 4 characters of a sensitive value."""
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]


def mask_url_creds(value: str) -> str:
    """Mask user:pass@ credentials embedded in proxy URLs."""
    return re.sub(r"://[^/@\s]+@", "://****@", value)


def collect_env() -> dict:
    out = {}
    for key in sorted(os.environ):
        val = os.environ[key]
        if key.startswith(ENV_PREFIXES) or key in ENV_EXACT:
            out[key] = mask(val) if SENSITIVE.search(key) else val
        elif key in PROXY_VARS:
            out[key] = mask_url_creds(val)
    return out


def session_url() -> str:
    sid = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID", "")
    if sid.startswith("cse_"):
        return "https://claude.ai/code/session_" + sid[len("cse_"):]
    return ""


def tool_version(cmd: list) -> str:
    if shutil.which(cmd[0]) is None:
        return "(not installed)"
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        line = (r.stdout or r.stderr).strip().splitlines()
        return line[0] if line else "(no output)"
    except Exception as exc:  # noqa: BLE001 - diagnostics, keep going
        return f"(error: {exc})"


def git_context() -> dict:
    ctx = {}
    for label, cmd in (("branch", ["git", "rev-parse", "--abbrev-ref", "HEAD"]),
                       ("remote", ["git", "remote", "get-url", "origin"])):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            ctx[label] = r.stdout.strip() if r.returncode == 0 else "(none)"
        except Exception:
            ctx[label] = "(unavailable)"
    return ctx


def system_info() -> dict:
    info = {
        "os": platform.platform(),
        "kernel": platform.release(),
        "arch": platform.machine(),
        "hostname_masked": mask(socket.gethostname()),
        "cpus": os.cpu_count(),
    }
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith(("MemTotal", "MemAvailable")):
                    key, _, rest = line.partition(":")
                    info[key.strip()] = rest.strip()
    except OSError:
        pass
    for label, path in (("disk_free_cwd", os.getcwd()),
                        ("disk_free_home", os.path.expanduser("~"))):
        try:
            du = shutil.disk_usage(path)
            info[label] = f"{du.free / 2**30:.1f} GiB free of {du.total / 2**30:.1f} GiB"
        except OSError:
            info[label] = "(unavailable)"
    return info


def diagnostics_tail(lines: int = 20) -> list:
    path = os.environ.get("CLAUDE_CODE_DIAGNOSTICS_FILE")
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, errors="replace") as fh:
            return [ln.rstrip("\n") for ln in fh.readlines()[-lines:]]
    except OSError:
        return []


def probe(url: str, timeout: float = 5.0) -> str:
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "sandbox-env-report/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return f"reachable (HTTP {resp.status})"
    except urllib.error.HTTPError as exc:
        return f"reachable (HTTP {exc.code})"  # server answered: network is open
    except Exception as exc:  # noqa: BLE001
        return f"blocked/unreachable ({exc.__class__.__name__})"


def infer_policy(results: dict) -> str:
    ok = {u for u, r in results.items() if r.startswith("reachable")}
    registries = {"https://registry.npmjs.org", "https://pypi.org"}
    if ok >= set(PROBES):
        return "All (or Custom allowing all probed hosts)"
    if registries & ok and "https://github.com" in ok:
        return "Trusted-like (registries reachable; GitHub via scoped proxy)"
    if registries & ok:
        return "Trusted (package registries reachable, general egress blocked)"
    if ok == {"https://github.com"}:
        return "None/Trusted (only GitHub scoped-credential proxy reachable)"
    if not ok:
        return "None (all probed egress blocked)"
    return "Custom (mixed results)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument("--no-network", action="store_true",
                    help="skip HTTPS reachability probes")
    args = ap.parse_args()

    home = os.path.expanduser("~")
    cwd = os.getcwd()
    report = {
        "claude_env": collect_env(),
        "session_url": session_url(),
        "system": system_info(),
        "tools": {
            "git": tool_version(["git", "--version"]),
            "node": tool_version(["node", "--version"]),
            "python3": tool_version(["python3", "--version"]),
            "claude": tool_version(["claude", "--version"]),
        },
        "cwd": cwd,
        "home": home,
        "home_cwd_mismatch": not cwd.startswith(home),
        "git": git_context(),
        "diagnostics_tail": diagnostics_tail(),
    }
    if not args.no_network:
        report["network_probes"] = {u: probe(u) for u in PROBES}
        report["inferred_network_policy"] = infer_policy(report["network_probes"])

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("== Claude Code environment report (secrets masked) ==\n")
    print("-- Claude/proxy env vars --")
    if report["claude_env"]:
        for k, v in report["claude_env"].items():
            print(f"  {k}={v}")
    else:
        print("  (none found - this does not look like a Claude Code sandbox)")
    if report["session_url"]:
        print(f"\n  web session URL: {report['session_url']}")

    print("\n-- System --")
    for k, v in report["system"].items():
        print(f"  {k}: {v}")
    print(f"  cwd:  {cwd}")
    print(f"  HOME: {home}")
    if report["home_cwd_mismatch"]:
        print("  note: HOME is outside the workspace tree - ~/.claude lives at "
              f"{home}/.claude, not under {cwd}. Resolve paths via $HOME or "
              "CLAUDE_CONFIG_DIR, never the cwd.")

    print("\n-- Tool versions --")
    for k, v in report["tools"].items():
        print(f"  {k}: {v}")

    print("\n-- Git context --")
    for k, v in report["git"].items():
        print(f"  {k}: {v}")

    if report["diagnostics_tail"]:
        print("\n-- Diagnostics file tail (CLAUDE_CODE_DIAGNOSTICS_FILE) --")
        for line in report["diagnostics_tail"]:
            print(f"  {line}")

    if not args.no_network:
        print("\n-- Network probes --")
        for u, r in report["network_probes"].items():
            print(f"  {u}: {r}")
        print(f"  inferred policy: {report['inferred_network_policy']}")

    print("\nReview before sharing; values matching ACCOUNT/ORG/EMAIL/TOKEN/etc. "
          "are already masked to their last 4 characters.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
