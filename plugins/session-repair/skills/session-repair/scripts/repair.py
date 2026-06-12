#!/usr/bin/env python3
"""repair.py - Repair a damaged Claude Code session JSONL file so it can be resumed.

Fixes applied (streaming, never loads the whole file into memory):
  * drop lines that are not valid JSON objects
  * remove empty text/thinking blocks from message.content (the #41992 corruption
    that makes a session permanently unresumable); if that leaves the content
    empty, or the line is an assistant line whose only payload was empty blocks,
    drop the whole line
  * drop lines with empty message.content ("" or [])
  * optionally drop all progress-type lines (--strip-progress, the fix for
    multi-GB progress bloat, issue #18905)
  * re-stitch parentUuid chains: any kept line whose parent was dropped is
    re-pointed at the dropped line's own parent (transitively), so the
    conversation tree stays connected

Default is a DRY RUN that only prints what would change. With --apply the
original file is first copied to FILE.bak-<timestamp>, then atomically replaced
by the repaired version.

Usage:
  python3 repair.py /path/to/session.jsonl                  # dry run (report only)
  python3 repair.py /path/to/session.jsonl --apply          # back up, then repair
  python3 repair.py FILE --apply --strip-progress           # also remove progress lines
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import time


def human(nbytes):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if nbytes < 1024 or unit == "TB":
            return "%.1f %s" % (nbytes, unit) if unit != "B" else "%d B" % nbytes
        nbytes /= 1024.0


def classify(raw, strip_progress):
    """Return (action, obj, notes). action in {'keep','drop','patch'}."""
    stripped = raw.strip()
    if not stripped:
        return "drop", None, ["blank line"]
    try:
        obj = json.loads(stripped)
    except (ValueError, UnicodeDecodeError):
        return "drop", None, ["unparseable JSON"]
    if not isinstance(obj, dict):
        return "drop", None, ["JSON line is not an object"]

    ltype = obj.get("type")
    if strip_progress and ltype == "progress":
        return "drop", obj, ["progress line (--strip-progress)"]

    notes = []
    msg = obj.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if content == "" or content == []:
            return "drop", obj, ["empty message.content"]
        if isinstance(content, list):
            cleaned = []
            removed = 0
            for block in content:
                # Empty TEXT blocks are the #41992 corruption. Empty thinking
                # blocks are only corrupt when UNSIGNED; signed empty thinking
                # blocks are normal in current transcript versions - keep them.
                if (
                    isinstance(block, dict)
                    and (
                        (block.get("type") == "text" and block.get("text", None) == "")
                        or (
                            block.get("type") == "thinking"
                            and block.get("thinking", None) == ""
                            and not block.get("signature")
                        )
                    )
                ):
                    removed += 1
                    continue
                cleaned.append(block)
            if removed:
                if not cleaned:
                    return "drop", obj, [
                        "all %d content block(s) were empty (#41992)" % removed
                    ]
                msg["content"] = cleaned
                notes.append("removed %d empty content block(s) (#41992)" % removed)
                return "patch", obj, notes
    return "keep", obj, notes


def resolve_parent(parent, dropped_parent_of):
    """Follow dropped uuids to the nearest kept ancestor (or None)."""
    seen = set()
    while parent in dropped_parent_of and parent not in seen:
        seen.add(parent)
        parent = dropped_parent_of[parent]
    return parent


def main():
    ap = argparse.ArgumentParser(
        description="Repair a damaged Claude Code session JSONL file (dry-run by default)."
    )
    ap.add_argument("file", help="Path to the session .jsonl file to repair.")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Actually write the repaired file. Copies FILE to FILE.bak-<timestamp> first. "
        "Without this flag, only a report is printed and nothing is modified.",
    )
    ap.add_argument(
        "--strip-progress",
        action="store_true",
        help="Also drop all progress-type lines (the multi-GB bloat fix, issue #18905).",
    )
    args = ap.parse_args()

    path = os.path.abspath(args.file)
    if not os.path.isfile(path):
        print("ERROR: no such file: %s" % path)
        sys.exit(2)

    orig_size = os.path.getsize(path)
    print("Repair target : %s" % path)
    print("Original size : %s" % human(orig_size))
    print("Mode          : %s" % ("APPLY (with backup)" if args.apply else "DRY RUN (no changes)"))
    print()

    # ---- Pass 1: classify every line; record parents of dropped lines ----
    dropped_parent_of = {}   # uuid of dropped line -> its parentUuid
    stats = {"keep": 0, "patch": 0, "drop": 0}
    drop_reasons = {}
    samples = []
    with open(path, "rb") as f:
        for lineno, raw in enumerate(f, 1):
            action, obj, notes = classify(raw, args.strip_progress)
            stats[action] += 1
            if action == "drop":
                reason = notes[0] if notes else "unknown"
                drop_reasons[reason] = drop_reasons.get(reason, 0) + 1
                if isinstance(obj, dict) and obj.get("uuid"):
                    dropped_parent_of[obj["uuid"]] = obj.get("parentUuid")
                if len(samples) < 15:
                    samples.append("line %d: DROP (%s)" % (lineno, "; ".join(notes)))
            elif action == "patch" and len(samples) < 15:
                samples.append("line %d: PATCH (%s)" % (lineno, "; ".join(notes)))

    restitch_planned = 0

    # ---- Pass 2: stream again, emit repaired lines ----
    tmp_path = None
    out = None
    if args.apply:
        fd, tmp_path = tempfile.mkstemp(
            prefix=os.path.basename(path) + ".repair.", dir=os.path.dirname(path)
        )
        out = os.fdopen(fd, "w", encoding="utf-8")
    try:
        with open(path, "rb") as f:
            for raw in f:
                action, obj, _ = classify(raw, args.strip_progress)
                if action == "drop":
                    continue
                parent = obj.get("parentUuid")
                if parent in dropped_parent_of:
                    new_parent = resolve_parent(parent, dropped_parent_of)
                    obj["parentUuid"] = new_parent
                    restitch_planned += 1
                    action = "patch"
                if out is not None:
                    if action == "patch":
                        out.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
                        out.write("\n")
                    else:
                        out.write(raw.decode("utf-8", errors="replace"))
                        if not raw.endswith(b"\n"):
                            out.write("\n")
        if out is not None:
            out.flush()
            os.fsync(out.fileno())
            out.close()
            out = None
    except BaseException:
        if out is not None:
            out.close()
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    # ---- Report ----
    print("Lines kept    : %d" % stats["keep"])
    print("Lines patched : %d (plus %d parentUuid re-stitches)" % (stats["patch"], restitch_planned))
    print("Lines dropped : %d" % stats["drop"])
    for reason, count in sorted(drop_reasons.items(), key=lambda kv: -kv[1]):
        print("    %6d  %s" % (count, reason))
    if samples:
        print("Sample of changes:")
        for s in samples:
            print("    %s" % s)
    print()

    if not args.apply:
        print("DRY RUN complete - no files were modified.")
        print("Re-run with --apply to back up and write the repaired file.")
        sys.exit(0)

    if stats["drop"] == 0 and stats["patch"] == 0 and restitch_planned == 0:
        print("Nothing to repair - file left untouched, no backup created.")
        os.unlink(tmp_path)
        sys.exit(0)

    backup = "%s.bak-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, backup)
    print("Backup written: %s" % backup)
    os.replace(tmp_path, path)
    new_size = os.path.getsize(path)
    print("Repaired file : %s (%s -> %s, %.1f%% of original)" % (
        path, human(orig_size), human(new_size), 100.0 * new_size / orig_size if orig_size else 0,
    ))
    print()
    print("Verify with: claude --resume %s" % os.path.basename(path).replace(".jsonl", ""))
    print("If anything looks wrong, restore the backup:")
    print("  cp %s %s" % (backup, path))


if __name__ == "__main__":
    main()
