#!/usr/bin/env python3
"""Read-only audit of the ~/.claude data directory.

Reports per-directory sizes, per-project session counts and ages,
top-10 largest files, orphaned session artifacts, and stale shell
snapshots. Makes no changes whatsoever.
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Directories that are actively used and reported as normal categories.
CATEGORY_DIRS = [
    "projects",
    "file-history",
    "debug",
    "paste-cache",
    "image-cache",
    "shell-snapshots",
    "session-env",
    "tasks",
    "plans",
    "backups",
    "feedback-bundles",
]
# Legacy directories no longer written by current Claude Code versions.
LEGACY_DIRS = ["todos", "statsig", "logs"]
# Never-touch items (reported, but flagged as protected).
PROTECTED = [
    "settings.json", "CLAUDE.md", "plugins", "skills", "agents", "commands",
    "history.jsonl", "stats-cache.json", "remote-settings.json",
]


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


def dir_stats(path: Path):
    """Return (total_bytes, file_count) for a directory tree (no symlink follow)."""
    total = 0
    count = 0
    if not path.exists():
        return 0, 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                st = os.lstat(os.path.join(root, name))
            except OSError:
                continue
            total += st.st_size
            count += 1
    return total, count


def age_days(mtime: float) -> float:
    return (time.time() - mtime) / 86400.0


def iter_files(path: Path):
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in files:
            p = Path(root) / name
            try:
                yield p, p.lstat()
            except OSError:
                continue


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--threshold-days", type=int, default=30,
                    help="age in days after which artifacts count as stale (default 30)")
    args = ap.parse_args()

    base = resolve_claude_dir()
    if not base.is_dir():
        print(f"error: Claude data directory not found at {base}", file=sys.stderr)
        return 1

    print(f"Claude data directory: {base}")
    print(f"Staleness threshold:   {args.threshold_days} days")
    print()

    total_bytes, total_files = dir_stats(base)
    print(f"TOTAL: {human(total_bytes)} across {total_files} files")
    print()

    # --- Category breakdown ---------------------------------------------
    print("== Category sizes ==")
    for name in CATEGORY_DIRS:
        size, count = dir_stats(base / name)
        if (base / name).exists():
            print(f"  {name:<18} {human(size):>10}  ({count} files)")
    legacy_total = 0
    for name in LEGACY_DIRS:
        p = base / name
        if p.exists():
            size, count = dir_stats(p)
            legacy_total += size
            print(f"  {name:<18} {human(size):>10}  ({count} files)  [LEGACY - no longer written]")
    print()

    # --- Projects breakdown ----------------------------------------------
    projects = base / "projects"
    known_sessions = set()
    if projects.is_dir():
        print("== Projects (transcripts) ==")
        rows = []
        for proj in sorted(projects.iterdir()):
            if not proj.is_dir():
                continue
            jsonls = list(proj.glob("*.jsonl"))
            known_sessions.update(j.stem for j in jsonls)
            size, _ = dir_stats(proj)
            ages = [age_days(j.lstat().st_mtime) for j in jsonls]
            newest = min(ages) if ages else float("nan")
            oldest = max(ages) if ages else float("nan")
            rows.append((size, proj.name, len(jsonls), newest, oldest))
        for size, name, n, newest, oldest in sorted(rows, reverse=True):
            span = f"ages {newest:.0f}-{oldest:.0f}d" if n else "no transcripts"
            print(f"  {name:<44} {human(size):>10}  {n:>4} sessions  {span}")
        print()

    # --- Top-10 largest files --------------------------------------------
    print("== Top 10 largest files ==")
    biggest = sorted(iter_files(base), key=lambda t: t[1].st_size, reverse=True)[:10]
    for p, st in biggest:
        print(f"  {human(st.st_size):>10}  {p.relative_to(base)}")
    print()

    # --- Orphaned artifacts ------------------------------------------------
    orphan_session_dirs = []
    if projects.is_dir():
        for proj in projects.iterdir():
            if not proj.is_dir():
                continue
            for sub in proj.iterdir():
                if sub.is_dir() and not (proj / (sub.name + ".jsonl")).exists():
                    orphan_session_dirs.append(sub)
    orphan_fh = []
    fh = base / "file-history"
    if fh.is_dir():
        for sub in fh.iterdir():
            if sub.is_dir() and sub.name not in known_sessions:
                orphan_fh.append(sub)
    orphan_bytes = sum(dir_stats(d)[0] for d in orphan_session_dirs + orphan_fh)
    print("== Orphaned artifacts ==")
    print(f"  session dirs without a matching .jsonl : {len(orphan_session_dirs)}")
    print(f"  file-history dirs for vanished sessions: {len(orphan_fh)}")
    print(f"  total orphaned size                    : {human(orphan_bytes)}")
    print()

    # --- Stale shell snapshots ---------------------------------------------
    snaps = base / "shell-snapshots"
    live = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    stale = []
    if snaps.is_dir():
        for p, st in iter_files(snaps):
            if live and live in p.name:
                continue  # belongs to the live session
            if age_days(st.st_mtime) > args.threshold_days:
                stale.append((p, st))
    stale_bytes = sum(st.st_size for _, st in stale)
    print("== Stale shell snapshots ==")
    print(f"  older than {args.threshold_days}d (excluding live session): "
          f"{len(stale)} files, {human(stale_bytes)}")
    print()

    print("Protected (never cleaned by this skill): "
          + ", ".join(["~/.claude.json"] + PROTECTED))
    return 0


if __name__ == "__main__":
    sys.exit(main())
