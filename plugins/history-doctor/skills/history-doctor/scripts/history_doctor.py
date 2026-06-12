#!/usr/bin/env python3
"""history_doctor.py - Inspect and repair Claude Code's prompt history and project map.

Targets two files:
  * <config>/history.jsonl  - every prompt ever entered (display text, timestamp,
    project path); powers up-arrow recall and influences `--continue` (#10063).
  * <config>/../.claude.json (i.e. ~/.claude.json) - ONLY its "projects" key,
    which holds per-project trust decisions and last-session metrics.
    ~/.claude.json ALSO holds OAuth credentials and global settings: this script
    never reads or writes any key other than "projects", and rewrites the file
    by mutating only that key in the parsed document.

Checks (default, read-only):
  * history.jsonl: malformed JSON lines (with line numbers); entries whose
    project path no longer exists on disk
  * ~/.claude.json "projects": entries whose path no longer exists (stale trust
    records)

Repairs:
  * --fix            back up BOTH files first (timestamped copies), then remove
                     malformed lines from history.jsonl
  * --prune-missing  (requires --fix) additionally remove history entries and
                     "projects" entries whose paths no longer exist

Usage:
  python3 history_doctor.py                      # report only, modifies nothing
  python3 history_doctor.py --fix                # remove malformed lines (with backups)
  python3 history_doctor.py --fix --prune-missing
"""

import argparse
import json
import os
import shutil
import sys
import time


def config_dir():
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(os.path.expanduser("~"), ".claude")


def entry_project(obj):
    """Best-effort project path from a history entry (format drifts across versions)."""
    for key in ("project", "cwd", "projectPath"):
        val = obj.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def backup(path):
    dst = "%s.bak-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, dst)
    return dst


def main():
    ap = argparse.ArgumentParser(
        description="Inspect and repair Claude Code history.jsonl and the projects map in ~/.claude.json."
    )
    ap.add_argument(
        "--fix",
        action="store_true",
        help="Back up both files, then remove malformed lines from history.jsonl. Without this flag nothing is modified.",
    )
    ap.add_argument(
        "--prune-missing",
        action="store_true",
        help="Additionally remove history entries and ~/.claude.json projects entries whose paths no longer exist. Requires --fix.",
    )
    args = ap.parse_args()

    if args.prune_missing and not args.fix:
        ap.error("--prune-missing requires --fix (it modifies files).")

    cdir = config_dir()
    history_path = os.path.join(cdir, "history.jsonl")
    claude_json_path = os.path.join(os.path.dirname(cdir), os.path.basename(cdir) + ".json")
    # Standard layout: config dir ~/.claude -> sibling file ~/.claude.json
    print("Claude config dir : %s" % cdir)
    print("history.jsonl     : %s%s" % (history_path, "" if os.path.isfile(history_path) else "  (MISSING)"))
    print("claude.json       : %s%s" % (claude_json_path, "" if os.path.isfile(claude_json_path) else "  (MISSING)"))
    print("Mode              : %s" % ("FIX" + (" + PRUNE-MISSING" if args.prune_missing else "") if args.fix else "REPORT ONLY"))
    print()

    problems = 0

    # ---------- history.jsonl ----------
    kept_lines = []
    malformed = []
    missing_path_lines = []  # (lineno, project)
    total_lines = 0
    if os.path.isfile(history_path):
        with open(history_path, "rb") as f:
            for lineno, raw in enumerate(f, 1):
                total_lines = lineno
                stripped = raw.strip()
                if not stripped:
                    malformed.append(lineno)
                    continue
                try:
                    obj = json.loads(stripped)
                    if not isinstance(obj, dict):
                        raise ValueError("not an object")
                except (ValueError, UnicodeDecodeError):
                    malformed.append(lineno)
                    continue
                proj = entry_project(obj)
                stale = proj is not None and not os.path.isdir(proj)
                if stale:
                    missing_path_lines.append((lineno, proj))
                if args.prune_missing and stale:
                    continue
                kept_lines.append(raw)

        print("history.jsonl: %d line(s) total" % total_lines)
        if malformed:
            problems += 1
            shown = ", ".join(map(str, malformed[:20])) + ("..." if len(malformed) > 20 else "")
            print("  MALFORMED: %d line(s) at line(s) %s" % (len(malformed), shown))
            print("  Malformed lines can break --continue and up-arrow recall (#10063).")
        else:
            print("  All lines are valid JSON.")
        if missing_path_lines:
            problems += 1
            stale_paths = {}
            for _ln, p in missing_path_lines:
                stale_paths[p] = stale_paths.get(p, 0) + 1
            print("  STALE: %d entry(ies) point at %d project path(s) that no longer exist:" % (len(missing_path_lines), len(stale_paths)))
            for p, c in sorted(stale_paths.items(), key=lambda kv: -kv[1])[:20]:
                print("    %5d  %s" % (c, p))
        else:
            print("  No entries point at missing project paths.")
    else:
        print("history.jsonl not found - nothing to check there.")
    print()

    # ---------- ~/.claude.json projects map ----------
    claude_doc = None
    stale_projects = []
    if os.path.isfile(claude_json_path):
        try:
            with open(claude_json_path, "r", encoding="utf-8") as f:
                claude_doc = json.load(f)
        except (ValueError, UnicodeDecodeError) as e:
            problems += 1
            print("claude.json: FAILED TO PARSE (%s)." % e)
            print("  This file holds OAuth and settings - do NOT auto-repair it; restore from")
            print("  %s/backups/ (pre-migration copies) or re-login." % cdir)
            claude_doc = None
        if isinstance(claude_doc, dict):
            projects = claude_doc.get("projects")
            if isinstance(projects, dict):
                for p in sorted(projects):
                    if not os.path.isdir(p):
                        stale_projects.append(p)
                print("claude.json projects map: %d entry(ies)" % len(projects))
                if stale_projects:
                    problems += 1
                    print("  STALE: %d entry(ies) whose paths no longer exist (stale trust records):" % len(stale_projects))
                    for p in stale_projects[:20]:
                        print("    %s" % p)
                else:
                    print("  All project paths exist.")
            else:
                print("claude.json has no 'projects' map (nothing to check).")
    else:
        print("claude.json not found - nothing to check there.")
    print()

    # ---------- apply fixes ----------
    if not args.fix:
        if problems:
            print("REPORT ONLY: found issues. Re-run with --fix (and optionally --prune-missing) to repair.")
        else:
            print("All clean. Nothing to do.")
        sys.exit(1 if problems else 0)

    changed_history = bool(malformed) or (args.prune_missing and bool(missing_path_lines))
    changed_claude = args.prune_missing and bool(stale_projects) and isinstance(claude_doc, dict)

    if not changed_history and not changed_claude:
        print("Nothing to fix - no files modified, no backups created.")
        sys.exit(0)

    if changed_history and os.path.isfile(history_path):
        b = backup(history_path)
        print("Backup: %s" % b)
        tmp = history_path + ".tmp-historydoctor"
        with open(tmp, "wb") as out:
            for raw in kept_lines:
                out.write(raw if raw.endswith(b"\n") else raw + b"\n")
        os.replace(tmp, history_path)
        removed = total_lines - len(kept_lines)
        print("history.jsonl rewritten: removed %d line(s) (%d malformed%s), kept %d." % (
            removed,
            len(malformed),
            (", %d stale-path" % len(missing_path_lines)) if args.prune_missing else "",
            len(kept_lines),
        ))

    if changed_claude:
        b = backup(claude_json_path)
        print("Backup: %s" % b)
        # Mutate ONLY the 'projects' key; every other key is written back untouched.
        for p in stale_projects:
            del claude_doc["projects"][p]
        tmp = claude_json_path + ".tmp-historydoctor"
        with open(tmp, "w", encoding="utf-8") as out:
            json.dump(claude_doc, out, indent=2, ensure_ascii=False)
            out.write("\n")
        os.replace(tmp, claude_json_path)
        print("claude.json rewritten: removed %d stale entry(ies) from the 'projects' map only." % len(stale_projects))

    print()
    print("Done. Backups are timestamped next to the originals - keep them until you")
    print("have verified up-arrow history and `claude --continue` behave as expected.")


if __name__ == "__main__":
    main()
