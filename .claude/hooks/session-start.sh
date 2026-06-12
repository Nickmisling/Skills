#!/bin/bash
set -euo pipefail

# Only run in remote Claude Code sessions
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Validate marketplace structure at session start to catch issues early
if command -v claude &>/dev/null; then
  claude plugin validate . 2>&1 || true
fi
