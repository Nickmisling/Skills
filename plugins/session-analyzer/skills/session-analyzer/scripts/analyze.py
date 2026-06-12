#!/usr/bin/env python3
"""Statistical analysis of a Claude Code session transcript (JSONL).

Streams the file exactly once, line-by-line, accumulating counters only —
the transcript itself is never held in memory, so multi-GB files are fine.

Stdlib-only, Python 3.
"""

import argparse
import heapq
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return "%.1f %s" % (n, unit) if unit != "B" else "%d B" % n
        n /= 1024.0


def analyze(path, top_n):
    stats = {
        "file": path,
        "total_lines": 0,
        "total_bytes": 0,
        "parse_errors": 0,
        "type_counts": Counter(),
        "type_bytes": Counter(),
        "role_counts": Counter(),
        "tokens": {"input_tokens": 0, "output_tokens": 0,
                   "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        "tool_calls": Counter(),
        "tool_result_bytes": Counter(),
        "sidechain_lines": 0,
        "meta_lines": 0,
        "compactions": [],          # [{timestamp, uuid}]
        "versions": Counter(),
        "first_ts": None,
        "last_ts": None,
        "session_ids": set(),
        "git_branches": set(),
        "cwds": set(),
    }

    # branch detection: count children per parentUuid (uuids are small strings;
    # this scales linearly with line count, not file size)
    children = Counter()

    # top-N tracking via bounded heaps: (key, seq, uuid, info);
    # seq breaks ties so the info dicts are never compared
    top_output = []   # by output tokens per assistant turn
    top_result = []   # by tool_result bytes per turn
    seq = 0

    # map tool_use_id -> tool name so result bytes can be attributed
    tool_id_name = {}
    MAX_TOOL_ID_MAP = 50000  # bound memory on pathological files

    with open(path, "rb") as fh:
        for raw in fh:
            stats["total_lines"] += 1
            stats["total_bytes"] += len(raw)
            line = raw.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                stats["parse_errors"] += 1
                continue
            if not isinstance(rec, dict):
                stats["parse_errors"] += 1
                continue

            rtype = rec.get("type", "unknown")
            stats["type_counts"][rtype] += 1
            stats["type_bytes"][rtype] += len(raw)

            if rec.get("isSidechain"):
                stats["sidechain_lines"] += 1
            if rec.get("isMeta"):
                stats["meta_lines"] += 1

            ts = rec.get("timestamp")
            dt = parse_ts(ts)
            if dt:
                if stats["first_ts"] is None or dt < stats["first_ts"]:
                    stats["first_ts"] = dt
                if stats["last_ts"] is None or dt > stats["last_ts"]:
                    stats["last_ts"] = dt

            for key, bag in (("sessionId", "session_ids"),
                             ("gitBranch", "git_branches"),
                             ("cwd", "cwds")):
                v = rec.get(key)
                if v and len(stats[bag]) < 100:
                    stats[bag].add(v)
            v = rec.get("version")
            if v:
                stats["versions"][str(v)] += 1

            uuid = rec.get("uuid")
            parent = rec.get("parentUuid")
            if parent:
                children[parent] += 1

            if rec.get("isCompactSummary"):
                stats["compactions"].append({"timestamp": ts, "uuid": uuid})

            msg = rec.get("message")
            if isinstance(msg, dict):
                role = msg.get("role")
                if role:
                    stats["role_counts"][role] += 1

                usage = msg.get("usage")
                if isinstance(usage, dict):
                    for k in stats["tokens"]:
                        v = usage.get(k)
                        if isinstance(v, (int, float)):
                            stats["tokens"][k] += int(v)
                    out_tok = usage.get("output_tokens") or 0
                    if out_tok:
                        seq += 1
                        item = (out_tok, seq, uuid or "?",
                                {"timestamp": ts, "output_tokens": out_tok})
                        if len(top_output) < top_n:
                            heapq.heappush(top_output, item)
                        elif item[0] > top_output[0][0]:
                            heapq.heapreplace(top_output, item)

                content = msg.get("content")
                if isinstance(content, list):
                    turn_result_bytes = 0
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "tool_use":
                            name = block.get("name", "unknown")
                            stats["tool_calls"][name] += 1
                            bid = block.get("id")
                            if bid and len(tool_id_name) < MAX_TOOL_ID_MAP:
                                tool_id_name[bid] = name
                        elif btype == "tool_result":
                            size = len(json.dumps(block.get("content", ""),
                                                  ensure_ascii=False))
                            turn_result_bytes += size
                            name = tool_id_name.get(block.get("tool_use_id"),
                                                    "unknown")
                            stats["tool_result_bytes"][name] += size
                    if turn_result_bytes:
                        seq += 1
                        item = (turn_result_bytes, seq, uuid or "?",
                                {"timestamp": ts,
                                 "result_bytes": turn_result_bytes})
                        if len(top_result) < top_n:
                            heapq.heappush(top_result, item)
                        elif item[0] > top_result[0][0]:
                            heapq.heapreplace(top_result, item)

    # branch points: uuids with more than one child (rewind/retry evidence)
    branch_points = [{"uuid": u, "children": c}
                     for u, c in children.items() if c > 1]
    branch_points.sort(key=lambda b: -b["children"])

    stats["branch_points"] = branch_points
    stats["top_output_turns"] = [
        dict(uuid=u, **info) for _, _, u, info in sorted(top_output, reverse=True)]
    stats["top_result_turns"] = [
        dict(uuid=u, **info) for _, _, u, info in sorted(top_result, reverse=True)]

    tok = stats["tokens"]
    denom = tok["input_tokens"] + tok["cache_read_input_tokens"] + \
        tok["cache_creation_input_tokens"]
    stats["cache_hit_ratio"] = (tok["cache_read_input_tokens"] / denom) if denom else 0.0

    if stats["first_ts"] and stats["last_ts"]:
        stats["duration_seconds"] = (stats["last_ts"] - stats["first_ts"]).total_seconds()
    else:
        stats["duration_seconds"] = None
    return stats


def to_jsonable(stats):
    out = dict(stats)
    out["type_counts"] = dict(stats["type_counts"])
    out["type_bytes"] = dict(stats["type_bytes"])
    out["role_counts"] = dict(stats["role_counts"])
    out["tool_calls"] = dict(stats["tool_calls"])
    out["tool_result_bytes"] = dict(stats["tool_result_bytes"])
    out["versions"] = dict(stats["versions"])
    out["session_ids"] = sorted(stats["session_ids"])
    out["git_branches"] = sorted(stats["git_branches"])
    out["cwds"] = sorted(stats["cwds"])
    out["first_ts"] = stats["first_ts"].isoformat() if stats["first_ts"] else None
    out["last_ts"] = stats["last_ts"].isoformat() if stats["last_ts"] else None
    out["branch_point_count"] = len(stats["branch_points"])
    out["branch_points"] = stats["branch_points"][:25]
    return out


def print_human(stats, top_n):
    p = print
    p("=== Session analysis: %s ===" % stats["file"])
    p("lines: %d   bytes: %s   parse errors: %d"
      % (stats["total_lines"], fmt_bytes(stats["total_bytes"]), stats["parse_errors"]))
    if stats["first_ts"]:
        p("span: %s -> %s  (%.1f min)"
          % (stats["first_ts"].isoformat(), stats["last_ts"].isoformat(),
             (stats["duration_seconds"] or 0) / 60.0))
    if stats["session_ids"]:
        p("session ids: %s" % ", ".join(sorted(stats["session_ids"])[:3]))
    if stats["versions"]:
        p("claude-code versions seen: %s" % ", ".join(sorted(stats["versions"])))
    if stats["git_branches"]:
        p("git branches: %s" % ", ".join(sorted(stats["git_branches"])))

    p("\n-- record types (count / bytes / byte share) --")
    total_b = stats["total_bytes"] or 1
    for rtype, cnt in stats["type_counts"].most_common():
        b = stats["type_bytes"][rtype]
        p("  %-24s %6d  %10s  %5.1f%%" % (rtype, cnt, fmt_bytes(b), 100.0 * b / total_b))

    p("\n-- message roles --")
    for role, cnt in stats["role_counts"].most_common():
        p("  %-24s %6d" % (role, cnt))

    tok = stats["tokens"]
    p("\n-- tokens (from message.usage) --")
    p("  input:        %12d" % tok["input_tokens"])
    p("  output:       %12d" % tok["output_tokens"])
    p("  cache create: %12d" % tok["cache_creation_input_tokens"])
    p("  cache read:   %12d" % tok["cache_read_input_tokens"])
    p("  cache-hit ratio (cache_read / all input-side tokens): %.1f%%"
      % (100.0 * stats["cache_hit_ratio"]))

    if stats["tool_calls"]:
        p("\n-- tool calls (count / total result bytes) --")
        for name, cnt in stats["tool_calls"].most_common():
            p("  %-24s %6d  %10s" % (name, cnt,
                                     fmt_bytes(stats["tool_result_bytes"].get(name, 0))))

    if stats["top_output_turns"]:
        p("\n-- top %d turns by output tokens --" % top_n)
        for t in stats["top_output_turns"]:
            p("  %8d tok  %s  %s" % (t["output_tokens"], t["timestamp"] or "?", t["uuid"]))
    if stats["top_result_turns"]:
        p("\n-- top %d turns by tool-result bytes --" % top_n)
        for t in stats["top_result_turns"]:
            p("  %10s  %s  %s" % (fmt_bytes(t["result_bytes"]), t["timestamp"] or "?",
                                  t["uuid"]))

    p("\n-- structure --")
    p("  sidechain (subagent) lines: %d" % stats["sidechain_lines"])
    p("  meta lines: %d" % stats["meta_lines"])
    p("  branch points (rewind/retry evidence): %d" % len(stats["branch_points"]))
    for bp in stats["branch_points"][:10]:
        p("    %s -> %d children" % (bp["uuid"], bp["children"]))
    p("  compaction events: %d" % len(stats["compactions"]))
    for c in stats["compactions"]:
        p("    %s  %s" % (c["timestamp"] or "?", c["uuid"] or "?"))


def main():
    parser = argparse.ArgumentParser(
        description="Stream-analyze a Claude Code session transcript (.jsonl).")
    parser.add_argument("file", help="Path to the session .jsonl transcript.")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit machine-readable JSON instead of the text report.")
    parser.add_argument("--top", type=int, default=5, metavar="N",
                        help="How many most-expensive turns to report (default 5).")
    args = parser.parse_args()

    try:
        stats = analyze(args.file, max(1, args.top))
    except FileNotFoundError:
        sys.exit("error: no such file: %s" % args.file)

    if args.as_json:
        json.dump(to_jsonable(stats), sys.stdout, indent=2, default=str)
        print()
    else:
        print_human(stats, max(1, args.top))


if __name__ == "__main__":
    main()
