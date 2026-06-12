#!/usr/bin/env python3
"""size_report.py - Find oversized Claude Code session files before they hang the CLI.

Ranks session .jsonl files by size across ~/.claude/projects/ (or one project),
and for every file at or above the threshold streams it line-by-line to build a
record-type histogram (count + bytes per type) showing WHAT is big: progress
entries (#18905), tool_results, attachments, etc. Also measures the sibling
<uuid>/subagents/ and <uuid>/tool-results/ dirs. Prints a recommended action per
oversized file. Files over 50 MB are known to hang the CLI (#21022, #22365).

Strictly read-only: never modifies, moves, or deletes anything.

Usage:
  python3 size_report.py                          # all projects, defaults
  python3 size_report.py --threshold-mb 50        # detail-scan files >= 50 MB
  python3 size_report.py --top 20                 # show 20 largest files
  python3 size_report.py --project /path/to/proj  # only that project's sessions
  python3 size_report.py --all                    # explicit: every project (default)
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

CRIT_MB = 50


def config_dir():
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(os.path.expanduser("~"), ".claude")


def encode_project_path(path):
    return re.sub(r"[^A-Za-z0-9-]", "-", os.path.abspath(path))


def human(nbytes):
    n = float(nbytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return "%d B" % n if unit == "B" else "%.1f %s" % (n, unit)
        n /= 1024.0


def dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def collect_sessions(projects_root, only_encoded=None):
    sessions = []
    if not os.path.isdir(projects_root):
        return sessions
    for proj in sorted(os.listdir(projects_root)):
        if only_encoded and proj != only_encoded:
            continue
        pdir = os.path.join(projects_root, proj)
        if not os.path.isdir(pdir):
            continue
        for entry in os.listdir(pdir):
            if entry.endswith(".jsonl"):
                fpath = os.path.join(pdir, entry)
                try:
                    size = os.path.getsize(fpath)
                except OSError:
                    continue
                sessions.append({"project": proj, "path": fpath, "size": size})
    return sessions


def detail_scan(fpath):
    """Stream the file; return per-type counts and bytes. Never loads whole file."""
    counts = Counter()
    bytes_by_type = Counter()
    with open(fpath, "rb") as f:
        for raw in f:
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
                ltype = obj.get("type", "(no type)") if isinstance(obj, dict) else "(non-object)"
            except (ValueError, UnicodeDecodeError):
                ltype = "(malformed)"
            counts[ltype] += 1
            bytes_by_type[ltype] += len(raw)
    return counts, bytes_by_type


def recommend(fpath, size, bytes_by_type):
    total = sum(bytes_by_type.values()) or 1
    prog = bytes_by_type.get("progress", 0)
    recs = []
    if prog / total > 0.3:
        recs.append(
            "Progress entries are %.1f%% of the bytes: strip them with the "
            "session-repair skill (repair.py FILE --apply --strip-progress). Do NOT "
            "delete the session - the conversation itself is small." % (100.0 * prog / total)
        )
    big_user = bytes_by_type.get("user", 0)
    if big_user / total > 0.6:
        recs.append(
            "user lines dominate (%.1f%% of bytes) - likely huge toolUseResult "
            "payloads. If the session is no longer needed for resume, archive the "
            "file (e.g. gzip to another location) and remove it from projects/."
            % (100.0 * big_user / total)
        )
    if bytes_by_type.get("attachment", 0) / total > 0.3:
        recs.append(
            "attachment lines are large - pasted files/images inflated the "
            "transcript; archive then delete if resume is not needed."
        )
    if not recs:
        recs.append(
            "No single record type dominates. If you do not need to resume this "
            "session, archive it (gzip elsewhere) and delete the original plus its "
            "sibling <uuid>/ dir; otherwise leave it alone."
        )
    if size > CRIT_MB * 1024 * 1024:
        recs.insert(
            0,
            "OVER %d MB: known to hang the CLI on resume/startup (#21022, #22365) - "
            "act on this file first." % CRIT_MB,
        )
    return recs


def main():
    ap = argparse.ArgumentParser(
        description="Rank Claude Code session files by size and explain what is bloating the big ones."
    )
    ap.add_argument(
        "--threshold-mb",
        type=float,
        default=50,
        help="Detail-scan (record-type byte histogram) every file at or above this size in MB (default: 50).",
    )
    ap.add_argument("--top", type=int, default=20, help="How many largest files to list (default: 20).")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--project", help="Only scan sessions belonging to this project path.")
    group.add_argument(
        "--all", action="store_true", help="Scan every project under the config dir (default behavior)."
    )
    args = ap.parse_args()

    cdir = config_dir()
    projects_root = os.path.join(cdir, "projects")
    only = encode_project_path(args.project) if args.project else None

    print("Claude config dir : %s" % cdir)
    print("Scope             : %s" % (("project %s (%s)" % (args.project, only)) if only else "all projects"))
    print("Detail threshold  : %.1f MB   (CLI hang threshold: %d MB, issues #21022/#22365)" % (args.threshold_mb, CRIT_MB))
    print()

    sessions = collect_sessions(projects_root, only)
    if not sessions:
        print("No session files found under %s" % projects_root)
        sys.exit(0)

    sessions.sort(key=lambda s: -s["size"])
    total_bytes = sum(s["size"] for s in sessions)
    print("%d session file(s), %s total. Top %d by size:" % (len(sessions), human(total_bytes), min(args.top, len(sessions))))
    print("%-10s  %-44s  %s" % ("SIZE", "SESSION", "PROJECT"))
    for s in sessions[: args.top]:
        flag = " <-- OVER 50 MB" if s["size"] > CRIT_MB * 1024 * 1024 else ""
        print("%-10s  %-44s  %s%s" % (human(s["size"]), os.path.basename(s["path"]), s["project"], flag))
    print()

    threshold = args.threshold_mb * 1024 * 1024
    large = [s for s in sessions if s["size"] >= threshold]
    if not large:
        print("No files at or above %.1f MB - nothing needs a detail scan. All clear." % args.threshold_mb)
        sys.exit(0)

    issues = 0
    for s in large:
        issues += 1
        print("=" * 72)
        print("FILE: %s  (%s)" % (s["path"], human(s["size"])))
        counts, bytes_by_type = detail_scan(s["path"])
        total = sum(bytes_by_type.values()) or 1
        print("Record types (count / bytes / share):")
        for t, b in bytes_by_type.most_common():
            print("  %-26s %8d  %10s  %5.1f%%" % (t, counts[t], human(b), 100.0 * b / total))
        sib = os.path.splitext(s["path"])[0]
        for sub in ("subagents", "tool-results"):
            d = os.path.join(sib, sub)
            if os.path.isdir(d):
                print("Sibling %-13s: %s" % (sub + "/", human(dir_size(d))))
        print("Recommended action:")
        for r in recommend(s["path"], s["size"], bytes_by_type):
            print("  - %s" % r)
        print()

    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
