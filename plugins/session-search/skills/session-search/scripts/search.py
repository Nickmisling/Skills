#!/usr/bin/env python3
"""Find and extract past Claude Code sessions across all projects.

Modes:
  --list-projects          list encoded project dirs with session stats
  QUERY [filters]          stream-grep user/assistant text content
  --extract UUID           render one session to Markdown or JSON

All transcript access is streaming and line-by-line; files are never loaded
into memory at once, except --extract which holds one slimmed record per
line of a single session (text + metadata only, tool payloads collapsed).

Stdlib-only, Python 3.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone


def claude_dir():
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    if cfg:
        return cfg
    return os.path.join(os.path.expanduser("~"), ".claude")


def encode_project_path(path):
    """Mirror Claude Code's encoding: '/' (and other punctuation) -> '-'.
    /home/user/Skills -> -home-user-Skills"""
    return re.sub(r"[^A-Za-z0-9-]", "-", os.path.abspath(path))


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_date_arg(s, name):
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    sys.exit("error: cannot parse %s date %r (use YYYY-MM-DD)" % (name, s))


def iter_text_blocks(message):
    """Yield only human-readable text from a message.content value.
    Skips tool_use/tool_result/thinking payloads so QUERY never matches
    base64 blobs or tool noise."""
    if not isinstance(message, dict):
        return
    content = message.get("content")
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    yield text


def project_dirs(base, project_filter):
    root = os.path.join(base, "projects")
    if not os.path.isdir(root):
        sys.exit("error: %s does not exist" % root)
    if project_filter:
        enc = encode_project_path(project_filter)
        candidates = [enc, project_filter]
        for c in candidates:
            full = os.path.join(root, c)
            if os.path.isdir(full):
                return [(c, full)]
        sys.exit("error: project %r not found under %s" % (project_filter, root))
    out = []
    for name in sorted(os.listdir(root)):
        full = os.path.join(root, name)
        if os.path.isdir(full):
            out.append((name, full))
    return out


def session_files(project_dir):
    for name in sorted(os.listdir(project_dir)):
        if name.endswith(".jsonl"):
            yield name[:-6], os.path.join(project_dir, name)


# --- --list-projects ----------------------------------------------------------


def list_projects(base):
    rows = []
    for name, full in project_dirs(base, None):
        count = 0
        total = 0
        oldest = newest = None
        for _uuid, path in session_files(full):
            count += 1
            st = os.stat(path)
            total += st.st_size
            mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
            if oldest is None or mtime < oldest:
                oldest = mtime
            if newest is None or mtime > newest:
                newest = mtime
        rows.append((name, count, total, oldest, newest))
    print("%-50s %8s %12s  %-10s  %-10s" % ("project (encoded)", "sessions",
                                            "bytes", "oldest", "newest"))
    for name, count, total, oldest, newest in rows:
        print("%-50s %8d %12d  %-10s  %-10s"
              % (name, count, total,
                 oldest.date().isoformat() if oldest else "-",
                 newest.date().isoformat() if newest else "-"))
    if not rows:
        print("(no projects found)")


# --- QUERY search ---------------------------------------------------------------


def snippet(text, query, width=90):
    idx = text.lower().find(query.lower())
    if idx < 0:
        idx = 0
    start = max(0, idx - width // 3)
    snip = text[start:start + width].replace("\n", " ").strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if start + width < len(text) else ""
    return prefix + snip + suffix


def search(base, query, project_filter, since, until, max_hits_per_session=3):
    qlower = query.lower()
    total_hits = 0
    sessions_hit = 0
    for proj_name, proj_dir in project_dirs(base, project_filter):
        for uuid, path in session_files(proj_dir):
            # cheap date prefilter on mtime: a file last modified before
            # --since cannot contain in-range records
            if since:
                mtime = datetime.fromtimestamp(os.stat(path).st_mtime,
                                               tz=timezone.utc)
                if mtime < since:
                    continue
            hits_here = 0
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    # fast reject before paying for json.loads
                    if qlower not in line.lower():
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(rec, dict):
                        continue
                    if rec.get("type") not in ("user", "assistant"):
                        continue
                    if rec.get("isMeta"):
                        continue
                    ts = parse_ts(rec.get("timestamp"))
                    if since and ts and ts < since:
                        continue
                    if until and ts and ts > until:
                        continue
                    for text in iter_text_blocks(rec.get("message")):
                        if qlower in text.lower():
                            if hits_here == 0:
                                sessions_hit += 1
                            hits_here += 1
                            total_hits += 1
                            print("%s  %s  [%s] %s\n    %s" % (
                                uuid, proj_name,
                                rec.get("type"),
                                rec.get("timestamp") or "?",
                                snippet(text, query)))
                            break
                    if hits_here >= max_hits_per_session:
                        break
    print("\n%d hit(s) across %d session(s)." % (total_hits, sessions_hit))
    if total_hits:
        print("Extract a full session with: --extract UUID --format md")


# --- --extract ---------------------------------------------------------------


def find_session(base, uuid, project_filter):
    for _name, proj_dir in project_dirs(base, project_filter):
        path = os.path.join(proj_dir, uuid + ".jsonl")
        if os.path.isfile(path):
            return path
    sys.exit("error: session %s not found" % uuid)


def slim_record(rec):
    """Keep only what rendering needs; collapse tool payloads to one-liners."""
    out = {
        "uuid": rec.get("uuid"),
        "parentUuid": rec.get("parentUuid"),
        "type": rec.get("type"),
        "timestamp": rec.get("timestamp"),
        "isSidechain": rec.get("isSidechain", False),
        "isCompactSummary": rec.get("isCompactSummary", False),
        "parts": [],
    }
    msg = rec.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, str):
            out["parts"].append(("text", content))
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    out["parts"].append(("text", block.get("text") or ""))
                elif btype == "thinking":
                    t = block.get("thinking") or ""
                    out["parts"].append(("thinking", "[thinking, %d chars]" % len(t)))
                elif btype == "tool_use":
                    inp = json.dumps(block.get("input", {}), ensure_ascii=False)
                    if len(inp) > 160:
                        inp = inp[:160] + "..."
                    out["parts"].append(("tool_use", "%s %s"
                                         % (block.get("name", "?"), inp)))
                elif btype == "tool_result":
                    payload = json.dumps(block.get("content", ""),
                                         ensure_ascii=False)
                    out["parts"].append(("tool_result",
                                         "[tool_result, %d bytes]" % len(payload)))
    return out


def extract(base, uuid, project_filter, fmt, out_path):
    path = find_session(base, uuid, project_filter)
    records = {}
    last_seen = []  # preserve file order for leaf selection
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict) or not rec.get("uuid"):
                continue
            if rec.get("type") not in ("user", "assistant", "system", "summary"):
                continue
            if rec.get("isMeta"):
                continue
            slim = slim_record(rec)
            records[slim["uuid"]] = slim
            last_seen.append(slim["uuid"])

    if not records:
        sys.exit("error: no renderable records in %s" % path)

    # leaves: uuids that are never a parent
    parents = {r["parentUuid"] for r in records.values() if r["parentUuid"]}
    leaves = [u for u in last_seen if u not in parents]
    # the live conversation ends at the most recently appended leaf
    leaf = leaves[-1] if leaves else last_seen[-1]
    suppressed_leaves = len(leaves) - 1 if leaves else 0

    # walk leaf -> root
    chain = []
    cur = leaf
    seen = set()
    while cur and cur in records and cur not in seen:
        seen.add(cur)
        chain.append(records[cur])
        cur = records[cur]["parentUuid"]
    chain.reverse()

    # branch points along any path (rewind evidence)
    child_count = {}
    for r in records.values():
        p = r["parentUuid"]
        if p:
            child_count[p] = child_count.get(p, 0) + 1
    branch_points = sum(1 for c in child_count.values() if c > 1)

    if fmt == "json":
        doc = {"sessionId": uuid, "source": path,
               "renderedRecords": len(chain),
               "totalRecords": len(records),
               "suppressedBranchLeaves": suppressed_leaves,
               "branchPoints": branch_points,
               "conversation": [
                   {"uuid": r["uuid"], "type": r["type"],
                    "timestamp": r["timestamp"],
                    "isSidechain": r["isSidechain"],
                    "isCompactSummary": r["isCompactSummary"],
                    "parts": [{"kind": k, "text": v} for k, v in r["parts"]]}
                   for r in chain]}
        rendered = json.dumps(doc, indent=2, ensure_ascii=False)
    else:
        lines = ["# Session %s" % uuid, "",
                 "Source: `%s`" % path,
                 "Rendered %d of %d records (leaf-to-root path)."
                 % (len(chain), len(records))]
        if suppressed_leaves or branch_points:
            lines.append("Note: %d branch point(s); %d abandoned branch leaf/leaves "
                         "suppressed (rewind/retry history not shown)."
                         % (branch_points, suppressed_leaves))
        lines.append("")
        for r in chain:
            ts = r["timestamp"] or "?"
            label = r["type"].capitalize()
            if r["isCompactSummary"]:
                label += " (compaction summary)"
            if r["isSidechain"]:
                label += " (sidechain)"
            lines.append("## %s — %s" % (label, ts))
            lines.append("")
            for kind, text in r["parts"]:
                if kind == "text":
                    lines.append(text)
                elif kind == "tool_use":
                    lines.append("> tool_use: `%s`" % text.replace("`", "'"))
                elif kind == "tool_result":
                    lines.append("> %s" % text)
                elif kind == "thinking":
                    lines.append("> %s" % text)
                lines.append("")
        rendered = "\n".join(lines)

    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(rendered + "\n")
        print("wrote %s (%d bytes, %d records rendered, %d suppressed branch "
              "leaves)" % (os.path.abspath(out_path), len(rendered),
                           len(chain), suppressed_leaves))
    else:
        print(rendered)


# --- main ----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Search and extract Claude Code sessions across projects.")
    parser.add_argument("query", nargs="?", default=None, metavar="QUERY",
                        help="Case-insensitive text to find in user/assistant "
                             "message text (tool payloads are not searched).")
    parser.add_argument("--project", default=None,
                        help="Limit to one project: real path or encoded dir name.")
    parser.add_argument("--since", default=None, metavar="DATE",
                        help="Only records on/after this date (YYYY-MM-DD).")
    parser.add_argument("--until", default=None, metavar="DATE",
                        help="Only records on/before this date (YYYY-MM-DD).")
    parser.add_argument("--list-projects", action="store_true",
                        help="List encoded project dirs with session counts, "
                             "sizes, and date ranges.")
    parser.add_argument("--extract", default=None, metavar="UUID",
                        help="Render one session's conversation (leaf-to-root "
                             "parentUuid path) instead of searching.")
    parser.add_argument("--format", default="md", choices=["md", "json"],
                        help="Output format for --extract (default md).")
    parser.add_argument("--out", default=None, metavar="FILE",
                        help="Write --extract output to FILE instead of stdout.")
    args = parser.parse_args()

    base = claude_dir()

    if args.list_projects:
        list_projects(base)
        return
    if args.extract:
        extract(base, args.extract, args.project, args.format, args.out)
        return
    if not args.query:
        parser.error("provide QUERY, --list-projects, or --extract UUID")

    since = parse_date_arg(args.since, "--since")
    until = parse_date_arg(args.until, "--until")
    if until:
        until = until.replace(hour=23, minute=59, second=59)
    search(base, args.query, args.project, since, until)


if __name__ == "__main__":
    main()
