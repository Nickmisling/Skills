#!/usr/bin/env python3
"""diagnose.py - Read-only health check for Claude Code session JSONL files.

Validates session transcripts line-by-line without ever loading a whole file
into memory. Detects the known corruption patterns that break `claude --resume`:

  * malformed JSON lines
  * empty text/content blocks (GitHub issue #41992 - permanently unresumable)
  * broken parentUuid chains (parents referenced but never defined)
  * orphaned session dirs (a <uuid>/ dir with no matching <uuid>.jsonl - #18311)
  * oversized files (>50 MB hangs the CLI - #21022/#22365; >10 MB = warning)
  * progress-entry bloat (record-type histogram - #18905)

Usage:
  python3 diagnose.py                         # scan all sessions of current project
  python3 diagnose.py SESSION_UUID            # diagnose one session by uuid
  python3 diagnose.py /path/to/session.jsonl  # diagnose a specific file
  python3 diagnose.py --project /some/path    # use that project dir instead of cwd

This script is strictly read-only. It never modifies, moves, or deletes files.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

WARN_MB = 10
CRIT_MB = 50

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def config_dir():
    """Resolve the Claude config dir: CLAUDE_CONFIG_DIR wins, else $HOME/.claude."""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(os.path.expanduser("~"), ".claude")


def encode_project_path(path):
    """Encode an absolute project path the way Claude Code names project dirs:
    every path separator / non [A-Za-z0-9-] character becomes '-'.
    e.g. /home/user/Skills -> -home-user-Skills
    """
    return re.sub(r"[^A-Za-z0-9-]", "-", os.path.abspath(path))


def human(nbytes):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if nbytes < 1024 or unit == "TB":
            return "%.1f %s" % (nbytes, unit) if unit != "B" else "%d B" % nbytes
        nbytes /= 1024.0


def find_empty_blocks(obj):
    """Return (critical, info) lists of descriptions for empty content blocks.

    Empty TEXT blocks (and fully empty message.content) are the #41992
    corruption. Empty THINKING blocks with a signature are normal in current
    transcript versions and are reported as informational only.
    """
    critical, info = [], []
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return critical, info
    content = msg.get("content")
    if content == "" or content == []:
        critical.append("empty message.content")
        return critical, info
    if isinstance(content, list):
        for i, block in enumerate(content):
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and block.get("text", None) == "":
                critical.append("empty text block at content[%d]" % i)
            elif btype == "thinking" and block.get("thinking", None) == "":
                if block.get("signature"):
                    info.append("empty signed thinking block at content[%d] (normal)" % i)
                else:
                    critical.append("empty unsigned thinking block at content[%d]" % i)
    return critical, info


def diagnose_file(path, verbose=True):
    """Stream one session file. Returns dict of findings."""
    findings = {
        "path": path,
        "size": os.path.getsize(path),
        "lines": 0,
        "malformed": [],          # line numbers
        "empty_blocks": [],       # (line_no, description, line_type)
        "empty_block_info": [],   # benign empty blocks (signed thinking)
        "types": Counter(),
        "type_bytes": Counter(),
        "defined_uuids": set(),
        "referenced_parents": {},  # parent_uuid -> first referencing line no
        "issues": [],
        "notes": [],
    }
    with open(path, "rb") as f:
        for lineno, raw in enumerate(f, 1):
            findings["lines"] = lineno
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except (ValueError, UnicodeDecodeError):
                findings["malformed"].append(lineno)
                continue
            if not isinstance(obj, dict):
                findings["malformed"].append(lineno)
                continue
            ltype = obj.get("type", "(no type)")
            findings["types"][ltype] += 1
            findings["type_bytes"][ltype] += len(raw)
            uid = obj.get("uuid")
            if uid:
                findings["defined_uuids"].add(uid)
            parent = obj.get("parentUuid")
            if parent and parent not in findings["referenced_parents"]:
                findings["referenced_parents"][parent] = lineno
            critical, info = find_empty_blocks(obj)
            for desc in critical:
                findings["empty_blocks"].append((lineno, desc, ltype))
            for desc in info:
                findings["empty_block_info"].append((lineno, desc, ltype))

    # Broken parent chains: parents referenced but never defined anywhere.
    findings["missing_parents"] = {
        p: ln
        for p, ln in findings["referenced_parents"].items()
        if p not in findings["defined_uuids"]
    }

    # Assemble issue list
    size_mb = findings["size"] / (1024.0 * 1024.0)
    if size_mb > CRIT_MB:
        findings["issues"].append(
            "CRITICAL: file is %s (>%d MB hangs the CLI - issues #21022/#22365)"
            % (human(findings["size"]), CRIT_MB)
        )
    elif size_mb > WARN_MB:
        findings["issues"].append(
            "WARN: file is %s (>%d MB; watch for runaway growth)"
            % (human(findings["size"]), WARN_MB)
        )
    if findings["malformed"]:
        findings["issues"].append(
            "CRITICAL: %d malformed JSON line(s) at line(s) %s"
            % (
                len(findings["malformed"]),
                ", ".join(map(str, findings["malformed"][:20]))
                + ("..." if len(findings["malformed"]) > 20 else ""),
            )
        )
    if findings["empty_blocks"]:
        sample = "; ".join(
            "line %d: %s (%s line)" % (ln, d, t)
            for ln, d, t in findings["empty_blocks"][:10]
        )
        findings["issues"].append(
            "CRITICAL: %d empty content block(s) - the #41992 corruption that makes "
            "resume fail with an API error. %s" % (len(findings["empty_blocks"]), sample)
        )
    if findings["empty_block_info"]:
        findings["notes"].append(
            "INFO: %d empty signed thinking block(s) - normal in current transcript "
            "versions, not the #41992 corruption, no action needed."
            % len(findings["empty_block_info"])
        )
    if findings["missing_parents"]:
        sample = "; ".join(
            "parent %s first referenced at line %d" % (p, ln)
            for p, ln in list(findings["missing_parents"].items())[:5]
        )
        findings["issues"].append(
            "WARN: %d parentUuid value(s) referenced but never defined (broken chain; "
            "rewind/branch history may be lost). %s"
            % (len(findings["missing_parents"]), sample)
        )
    total_bytes = sum(findings["type_bytes"].values()) or 1
    prog_bytes = findings["type_bytes"].get("progress", 0)
    if prog_bytes / total_bytes > 0.5 and findings["size"] > 1024 * 1024:
        findings["issues"].append(
            "WARN: progress entries are %.1f%% of file bytes (progress bloat, issue "
            "#18905 - one reported 3.8 GB file was 99.6%% progress lines). Strip with "
            "the session-repair skill (--strip-progress)." % (100.0 * prog_bytes / total_bytes)
        )

    if verbose:
        print_report(findings)
    return findings


def print_report(f):
    print("=" * 72)
    print("Session file: %s" % f["path"])
    print("Size: %s   Lines: %d" % (human(f["size"]), f["lines"]))
    print("Record-type histogram (count / bytes):")
    for t, c in f["types"].most_common():
        print("  %-28s %8d  %10s" % (t, c, human(f["type_bytes"][t])))
    sib = os.path.splitext(f["path"])[0]
    if os.path.isdir(sib):
        for sub in ("subagents", "tool-results"):
            d = os.path.join(sib, sub)
            if os.path.isdir(d):
                n = sum(len(files) for _, _, files in os.walk(d))
                print("  sibling dir %s/: %d file(s)" % (sub, n))
    for note in f["notes"]:
        print("  - %s" % note)
    if f["issues"]:
        print("ISSUES:")
        for issue in f["issues"]:
            print("  - %s" % issue)
    else:
        print("Health: OK - no problems detected")
    print()


def scan_project(project_path):
    cdir = config_dir()
    encoded = encode_project_path(project_path)
    proj_dir = os.path.join(cdir, "projects", encoded)
    print("Claude config dir : %s" % cdir)
    print("Project path      : %s" % os.path.abspath(project_path))
    print("Expected encoding : %s" % encoded)
    print("Expected dir      : %s" % proj_dir)
    projects_root = os.path.join(cdir, "projects")
    if not os.path.isdir(proj_dir):
        print("PROBLEM: expected project dir does not exist.")
        if os.path.isdir(projects_root):
            print("Existing project dirs under %s:" % projects_root)
            for d in sorted(os.listdir(projects_root)):
                print("  %s" % d)
            print(
                "If a near-match exists, you likely have a path-encoding mismatch "
                "(symlinked cwd or symlinked .git - issues #18311/#33912/#45753)."
            )
        return 1
    print()
    entries = sorted(os.listdir(proj_dir))
    jsonl_stems = {e[:-6] for e in entries if e.endswith(".jsonl")}
    dirs = {e for e in entries if os.path.isdir(os.path.join(proj_dir, e)) and UUID_RE.match(e)}
    orphans = dirs - jsonl_stems
    if orphans:
        print(
            "ORPHANED SESSION DIR(S) (uuid dir exists but <uuid>.jsonl is missing - the "
            "#18311 'No conversation found' cause):"
        )
        for o in sorted(orphans):
            print("  %s" % os.path.join(proj_dir, o))
        print()
    bad = 0
    found_any = False
    for e in entries:
        if e.endswith(".jsonl"):
            found_any = True
            f = diagnose_file(os.path.join(proj_dir, e))
            if f["issues"]:
                bad += 1
    if not found_any:
        print("No session .jsonl files found in %s" % proj_dir)
    print("Scan complete. %d session file(s) with issues." % bad)
    return 1 if (bad or orphans) else 0


def main():
    ap = argparse.ArgumentParser(
        description="Read-only diagnosis of Claude Code session files.",
        epilog="With no arguments, scans every session of the current project.",
    )
    ap.add_argument(
        "target",
        nargs="?",
        help="Session UUID or path to a .jsonl session file. Omit to scan the whole project.",
    )
    ap.add_argument(
        "--project",
        default=os.getcwd(),
        help="Project path to resolve sessions against (default: current directory).",
    )
    args = ap.parse_args()

    if not args.target:
        sys.exit(scan_project(args.project))

    # Explicit file path?
    if os.path.isfile(args.target):
        f = diagnose_file(args.target)
        sys.exit(1 if f["issues"] else 0)

    # Treat as a session UUID: look in this project first, then all projects.
    cdir = config_dir()
    candidates = [
        os.path.join(cdir, "projects", encode_project_path(args.project), args.target + ".jsonl")
    ]
    projects_root = os.path.join(cdir, "projects")
    if os.path.isdir(projects_root):
        for d in sorted(os.listdir(projects_root)):
            candidates.append(os.path.join(projects_root, d, args.target + ".jsonl"))
    for c in candidates:
        if os.path.isfile(c):
            f = diagnose_file(c)
            sys.exit(1 if f["issues"] else 0)

    print("Session %r not found as a file or as <uuid>.jsonl under %s" % (args.target, projects_root))
    # Orphan check: dir exists without jsonl?
    if os.path.isdir(projects_root):
        for d in sorted(os.listdir(projects_root)):
            orphan = os.path.join(projects_root, d, args.target)
            if os.path.isdir(orphan):
                print(
                    "FOUND ORPHANED DIR: %s exists but %s.jsonl does not - this is the "
                    "#18311 'No conversation found' failure mode." % (orphan, orphan)
                )
                sys.exit(1)
    sys.exit(2)


if __name__ == "__main__":
    main()
