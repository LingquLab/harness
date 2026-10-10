#!/usr/bin/env bash
set -u

usage() {
    echo "Usage:" >&2
    echo "  ./start-bridge.sh sessions [config-file]" >&2
    echo "  ./start-bridge.sh <doctor|bind|run|open|status|acknowledge-recovery> <session-id> [config-file]" >&2
}

command_name="${1:-}"
session_id=""
config_file="config.local.json"
case "$command_name" in
    sessions)
        [[ $# -le 2 ]] || { usage; exit 2; }
        config_file="${2:-config.local.json}"
        ;;
    doctor|bind|run|open|status|acknowledge-recovery)
        [[ $# -ge 2 && $# -le 3 ]] || { usage; exit 2; }
        session_id="$2"
        config_file="${3:-config.local.json}"
        ;;
    *) usage; exit 2 ;;
esac

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir" || exit 1

log_dir="${BRIDGE_LOG_DIR:-$script_dir/.cac}"
mkdir -p -- "$log_dir" || exit 1
log_suffix="${session_id:+-$session_id}"
log_file="$log_dir/bridge-$command_name$log_suffix.log"
exec > >(tee -a "$log_file") 2>&1
echo "Bridge log: $log_file"

if [[ ! -f "$config_file" ]]; then
    cp -- config.example.json "$config_file" || exit 1
    echo "Created $config_file. Set access_key and repository cwd before running." >&2
    exit 1
fi

export PYTHONUNBUFFERED=1
python_args=(-m cross_zone --config "$config_file")
[[ -z "$session_id" ]] || python_args+=(--session "$session_id")
python_args+=("$command_name")
if command -v py >/dev/null 2>&1; then
    exec py -3 "${python_args[@]}"
elif command -v python >/dev/null 2>&1; then
    exec python "${python_args[@]}"
else
    echo "Python 3 was not found in PATH." >&2
    exit 127
fi
