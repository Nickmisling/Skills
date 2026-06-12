#!/usr/bin/env python3
"""Collect a complete Claude Code session bundle into a portable tar.gz archive.

Gathers the main transcript, subagent transcripts, spilled tool results,
pre-edit file-history snapshots, and matching history.jsonl prompt lines,
plus a manifest.json. Streams everything line-by-line; never loads whole
files into memory. Optionally redacts likely secrets in the archived copies
(originals are never modified).

Stdlib-only, Python 3.
"""

import argparse
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

# --- secret redaction -------------------------------------------------------

REDACTION_PATTERNS = [
    # AWS access key ids
    (re.compile(r"(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}"), "[REDACTED:AWS_KEY_ID]"),
    # AWS secret-ish assignments
    (re.compile(r"(?i)(aws_secret_access_key\s*[=:]\s*)[A-Za-z0-9/+=]{30,}"),
     r"\1[REDACTED:AWS_SECRET]"),
    # GitHub tokens
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "[REDACTED:GITHUB_PAT]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "[REDACTED:GITHUB_PAT]"),
    (re.compile(r"gh[ousr]_[A-Za-z0-9]{20,}"), "[REDACTED:GITHUB_TOKEN]"),
    # sk- style API keys (OpenAI, Anthropic sk-ant-..., Stripe sk_live_...)
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"), "[REDACTED:ANTHROPIC_KEY]"),
    (re.compile(r"sk-[A-Za-z0-9_-]{16,}"), "[REDACTED:SK_KEY]"),
    (re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{16,}"), "[REDACTED:STRIPE_KEY]"),
    # Bearer tokens
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{16,}"), r"\1[REDACTED:BEARER]"),
    # Slack tokens
    (re.compile(r"xox[abposr]-[A-Za-z0-9-]{10,}"), "[REDACTED:SLACK_TOKEN]"),
    # PEM private key blocks (may appear with \n escapes inside JSON strings)
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                re.DOTALL), "[REDACTED:PEM_PRIVATE_KEY]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:\\n|[^-])*?-----END [A-Z ]*PRIVATE KEY-----"),
     "[REDACTED:PEM_PRIVATE_KEY]"),
    # password= / passwd: assignments
    (re.compile(r"(?i)(pass(?:word|wd)?\s*[=:]\s*[\"']?)[^\s\"'&,;]{4,}"),
     r"\1[REDACTED:PASSWORD]"),
    # generic api_key / token / secret assignments
    (re.compile(r"(?i)\b((?:api[_-]?key|auth[_-]?token|access[_-]?token|client[_-]?secret)"
                r"\s*[=:]\s*[\"']?)[A-Za-z0-9._~+/-]{12,}"),
     r"\1[REDACTED:CREDENTIAL]"),
]


def redact_line(line, counter):
    for pattern, replacement in REDACTION_PATTERNS:
        line, n = pattern.subn(replacement, line)
        if n:
            counter[0] += n
    return line


# --- path resolution ---------------------------------------------------------


def claude_dir():
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    if cfg:
        return cfg
    return os.path.join(os.path.expanduser("~"), ".claude")


def encode_project_path(path):
    """Encode an absolute project path the way Claude Code does for
    ~/.claude/projects/ directory names (every '/' and '.' etc. -> '-')."""
    return re.sub(r"[^A-Za-z0-9-]", "-", os.path.abspath(path))


def find_project_dir(base, project, session_uuid):
    projects_root = os.path.join(base, "projects")
    if project:
        candidate = os.path.join(projects_root, encode_project_path(project))
        if os.path.isdir(candidate):
            return candidate
        # maybe the user passed the encoded name directly
        candidate = os.path.join(projects_root, project)
        if os.path.isdir(candidate):
            return candidate
        sys.exit("error: no project directory found for %r under %s" % (project, projects_root))
    if not os.path.isdir(projects_root):
        sys.exit("error: %s does not exist" % projects_root)
    if session_uuid:
        for name in sorted(os.listdir(projects_root)):
            if os.path.isfile(os.path.join(projects_root, name, session_uuid + ".jsonl")):
                return os.path.join(projects_root, name)
        sys.exit("error: session %s not found in any project under %s" % (session_uuid, projects_root))
    sys.exit("error: pass --project or a SESSION_UUID so the project can be located")


# --- streaming copy ----------------------------------------------------------


def stream_copy(src, dst, redact, counter):
    """Copy src -> dst line-by-line, optionally redacting. Returns (bytes, lines)."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    total = 0
    lines = 0
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        for raw in fin:
            lines += 1
            if redact:
                try:
                    text = raw.decode("utf-8")
                    text = redact_line(text, counter)
                    raw = text.encode("utf-8")
                except UnicodeDecodeError:
                    pass  # binary-ish line: copy verbatim
            fout.write(raw)
            total += len(raw)
    return total, lines


def copy_tree(src_dir, dst_dir, redact, counter, files_meta):
    for root, _dirs, files in os.walk(src_dir):
        for fname in files:
            src = os.path.join(root, fname)
            rel = os.path.relpath(src, src_dir)
            dst = os.path.join(dst_dir, rel)
            size, _ = stream_copy(src, dst, redact, counter)
            files_meta.append({"path": os.path.relpath(dst_dir, files_meta_base[0]) + "/" + rel,
                               "bytes": size})


files_meta_base = [""]  # set in main; ugly but keeps copy_tree signature small


# --- transcript scan for manifest --------------------------------------------


def scan_transcript(path):
    """Single streaming pass over a transcript for manifest data."""
    first_ts = last_ts = None
    versions = set()
    lines = 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            lines += 1
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = rec.get("timestamp")
            if ts:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts
            v = rec.get("version")
            if v:
                versions.add(str(v))
    return lines, first_ts, last_ts, sorted(versions)


# --- main ---------------------------------------------------------------------


def collect_session(base, project_dir, session_uuid, staging, redact, counter):
    """Copy all artifacts for one session into staging/<uuid>/. Returns manifest entry."""
    dest_root = os.path.join(staging, session_uuid)
    entry = {"sessionId": session_uuid, "files": []}
    files_meta_base[0] = staging

    main_jsonl = os.path.join(project_dir, session_uuid + ".jsonl")
    if not os.path.isfile(main_jsonl):
        print("warning: missing main transcript %s" % main_jsonl, file=sys.stderr)
        return None
    size, lines = stream_copy(main_jsonl, os.path.join(dest_root, session_uuid + ".jsonl"),
                              redact, counter)
    entry["files"].append({"path": "%s/%s.jsonl" % (session_uuid, session_uuid), "bytes": size})
    entry["lineCount"] = lines

    _, first_ts, last_ts, versions = scan_transcript(main_jsonl)
    entry["firstTimestamp"] = first_ts
    entry["lastTimestamp"] = last_ts
    entry["claudeCodeVersions"] = versions

    # sibling dir: subagents/ and tool-results/
    sibling = os.path.join(project_dir, session_uuid)
    for sub in ("subagents", "tool-results"):
        src = os.path.join(sibling, sub)
        if os.path.isdir(src):
            copy_tree(src, os.path.join(dest_root, sub), redact, counter, entry["files"])

    # file-history snapshots
    fh_dir = os.path.join(base, "file-history", session_uuid)
    if os.path.isdir(fh_dir):
        copy_tree(fh_dir, os.path.join(dest_root, "file-history"), redact, counter,
                  entry["files"])

    # matching history.jsonl lines
    history = os.path.join(base, "history.jsonl")
    if os.path.isfile(history):
        out_path = os.path.join(dest_root, "history-extract.jsonl")
        n = 0
        with open(history, "r", encoding="utf-8", errors="replace") as fin:
            buf = []
            for line in fin:
                if session_uuid in line:
                    if redact:
                        line = redact_line(line, counter)
                    buf.append(line)
                    n += 1
            if buf:
                with open(out_path, "w", encoding="utf-8") as fout:
                    fout.writelines(buf)
                entry["files"].append({
                    "path": "%s/history-extract.jsonl" % session_uuid,
                    "bytes": os.path.getsize(out_path),
                })
        entry["historyLines"] = n

    return entry


def main():
    parser = argparse.ArgumentParser(
        description="Collect a Claude Code session bundle into a portable tar.gz.")
    parser.add_argument("session_uuid", nargs="?", default=None, metavar="SESSION_UUID",
                        help="Session UUID to collect (omit with --all-project).")
    parser.add_argument("--project", default=None,
                        help="Project path (e.g. /home/user/Skills) or encoded dir name. "
                             "If omitted, all projects are searched for the UUID.")
    parser.add_argument("--out", default=".",
                        help="Directory to write the archive into (default: cwd).")
    parser.add_argument("--redact", action="store_true",
                        help="Mask likely secrets (AWS/GitHub/API keys, Bearer tokens, "
                             "PEM blocks, passwords) in the archived copies. "
                             "Originals are never modified.")
    parser.add_argument("--all-project", action="store_true",
                        help="Bundle every session of the project given by --project.")
    args = parser.parse_args()

    if not args.session_uuid and not args.all_project:
        parser.error("provide SESSION_UUID or use --all-project with --project")
    if args.all_project and not args.project:
        parser.error("--all-project requires --project")

    base = claude_dir()
    project_dir = find_project_dir(base, args.project, args.session_uuid)

    if args.all_project:
        uuids = sorted(f[:-6] for f in os.listdir(project_dir) if f.endswith(".jsonl"))
        if not uuids:
            sys.exit("error: no sessions found in %s" % project_dir)
    else:
        uuids = [args.session_uuid]

    counter = [0]  # redaction hit count
    staging = tempfile.mkdtemp(prefix="claude-session-bundle-")
    try:
        sessions = []
        for uuid in uuids:
            entry = collect_session(base, project_dir, uuid, staging, args.redact,
                                    counter)
            if entry:
                sessions.append(entry)
        if not sessions:
            sys.exit("error: nothing collected")

        manifest = {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "projectDir": project_dir,
            "redacted": bool(args.redact),
            "redactionCount": counter[0],
            "sessions": sessions,
        }
        with open(os.path.join(staging, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)

        os.makedirs(args.out, exist_ok=True)
        label = uuids[0] if len(uuids) == 1 else os.path.basename(project_dir)
        suffix = "-redacted" if args.redact else ""
        archive = os.path.join(args.out, "claude-session-%s%s.tar.gz" % (label, suffix))
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(staging, arcname="claude-session-%s" % label)

        total_bytes = sum(f["bytes"] for s in sessions for f in s["files"])
        print("archive: %s" % os.path.abspath(archive))
        print("sessions bundled: %d" % len(sessions))
        print("payload bytes (pre-compression): %d" % total_bytes)
        if args.redact:
            print("redactions applied: %d" % counter[0])
        else:
            print("WARNING: archive is NOT redacted; transcripts are plaintext and may "
                  "contain secrets. Re-run with --redact before sharing.")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    main()
