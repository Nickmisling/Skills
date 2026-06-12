#!/usr/bin/env python3
"""Selectively clean the ~/.claude data directory.

DRY-RUN BY DEFAULT: prints exactly what --apply would delete and how much
space it would free. Every category is opt-in via its own flag; with no
category flags the script does nothing.

Never touches: ~/.claude.json, settings.json, CLAUDE.md, plugins/, skills/,
agents/, commands/, history.jsonl, stats-cache.json, remote-settings.json,
or shell snapshots belonging to the live session.
"""

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

LEGACY_DIRS = ["todos", "statsig", "logs"]


def resolve_claude_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude"


def human(n: int) -> str:
    f = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if f < 1024 or unit == "TiB":
            return f"{f:.1f} {unit}" if unit != "B" else f"{int(f)} B"
        f /= 1024
    return f"{f:.1f} TiB"


def tree_size(path: Path) -> int:
    if path.is_file() or path.is_symlink():
        try:
            return path.lstat().st_size
        except OSError:
            return 0
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total


def collect(base: Path, args) -> list:
    """Return a list of (category, Path) deletion targets."""
    targets = []

    if args.legacy:
        for name in LEGACY_DIRS:
            p = base / name
            if p.exists():
                targets.append(("legacy", p))

    if args.debug_logs:
        p = base / "debug"
        if p.is_dir():
            for child in sorted(p.iterdir()):
                targets.append(("debug-logs", child))

    if args.orphans:
        projects = base / "projects"
        known = set()
        if projects.is_dir():
            for proj in projects.iterdir():
                if not proj.is_dir():
                    continue
                for j in proj.glob("*.jsonl"):
                    known.add(j.stem)
                for sub in proj.iterdir():
                    if sub.is_dir() and not (proj / (sub.name + ".jsonl")).exists():
                        targets.append(("orphans", sub))
        fh = base / "file-history"
        if fh.is_dir():
            for sub in fh.iterdir():
                if sub.is_dir() and sub.name not in known:
                    targets.append(("orphans", sub))

    if args.stale_snapshots is not None:
        snaps = base / "shell-snapshots"
        live = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
        cutoff = time.time() - args.stale_snapshots * 86400
        if snaps.is_dir():
            for p in sorted(snaps.iterdir()):
                if live and live in p.name:
                    continue  # never touch the live session's snapshot
                try:
                    if p.lstat().st_mtime < cutoff:
                        targets.append(("stale-snapshots", p))
                except OSError:
                    continue

    if args.project:
        enc = args.project
        if "/" in enc or enc in ("", ".", ".."):
            print(f"error: --project expects an encoded name like "
                  f"-home-user-Skills, got {enc!r}", file=sys.stderr)
            sys.exit(2)
        proj = base / "projects" / enc
        if proj.is_dir():
            sessions = {j.stem for j in proj.glob("*.jsonl")}
            targets.append(("project", proj))
            fh = base / "file-history"
            if fh.is_dir():
                for sub in fh.iterdir():
                    if sub.is_dir() and sub.name in sessions:
                        targets.append(("project", sub))
        else:
            print(f"error: no such project directory: {proj}", file=sys.stderr)
            sys.exit(2)

    return targets


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually delete (default is dry-run)")
    ap.add_argument("--legacy", action="store_true",
                    help="remove legacy todos/, statsig/, logs/ directories")
    ap.add_argument("--orphans", action="store_true",
                    help="remove session dirs without a .jsonl and file-history "
                         "dirs for vanished sessions")
    ap.add_argument("--debug-logs", action="store_true",
                    help="empty the debug/ directory")
    ap.add_argument("--stale-snapshots", type=int, metavar="DAYS",
                    help="remove shell snapshots older than DAYS "
                         "(live session always skipped)")
    ap.add_argument("--project", metavar="ENCODED_NAME",
                    help="remove one project's transcripts and file-history; "
                         "encoded names start with '-', so use the equals "
                         "form: --project=-home-user-Skills "
                         "(prefer 'claude project purge' on CLI >= 2.1.124)")
    args = ap.parse_args()

    if not any([args.legacy, args.orphans, args.debug_logs,
                args.stale_snapshots is not None, args.project]):
        ap.print_help()
        print("\nNothing selected: pass at least one category flag.", file=sys.stderr)
        return 2

    base = resolve_claude_dir()
    if not base.is_dir():
        print(f"error: Claude data directory not found at {base}", file=sys.stderr)
        return 1

    targets = collect(base, args)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] Claude data directory: {base}\n")

    if not targets:
        print("Nothing to clean in the selected categories.")
        return 0

    total = 0
    freed = 0
    for category, path in targets:
        size = tree_size(path)
        total += size
        verb = "deleting" if args.apply else "would delete"
        print(f"  [{category:<15}] {verb} {path.relative_to(base)}  ({human(size)})")
        if args.apply:
            try:
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                freed += size
            except OSError as exc:
                print(f"    ! failed: {exc}", file=sys.stderr)

    print()
    if args.apply:
        print(f"Freed {human(freed)} ({len(targets)} items).")
    else:
        print(f"Would free {human(total)} ({len(targets)} items). "
              f"Re-run with --apply after the user confirms.")
    if args.project:
        print("note: history.jsonl lines and the ~/.claude.json project entry "
              "are NOT modified by this script; use 'claude project purge' "
              "(CLI >= 2.1.124) for a complete removal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
