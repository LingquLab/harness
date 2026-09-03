#!/usr/bin/env bash
# Read a private GitHub handoff issue through an existing HTTPS credential.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
  python_command=(python3)
elif command -v python >/dev/null 2>&1; then
  python_command=(python)
elif command -v py >/dev/null 2>&1; then
  python_command=(py -3)
else
  echo "github_get_issue: Python 3 is required" >&2
  exit 1
fi

exec "${python_command[@]}" "${script_dir}/github_issue.py" get "$@"
