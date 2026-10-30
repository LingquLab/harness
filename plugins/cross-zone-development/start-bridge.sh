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
workspace_dir="$PWD"
cd "$script_dir" || exit 1

log_dir="${BRIDGE_LOG_DIR:-$script_dir/.cac}"
mkdir -p -- "$log_dir" || exit 1
log_suffix="${session_id:+-$session_id}"
log_file="$log_dir/bridge-$command_name$log_suffix.log"
# Color only the terminal branch, after tee has saved the plain-text log.
color_bridge_output() {
    local line prefix message state_prefix state color=""
    local state_pattern='^Task state: (.* = )(PASS|FAIL)$'
    local log_pattern='^([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:,]+ (DEBUG|INFO|WARNING|ERROR|CRITICAL) )(.*)$'
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        if [[ "$line" =~ $log_pattern ]]; then
            prefix="${BASH_REMATCH[1]}"
            message="${BASH_REMATCH[3]}"
            if [[ "$message" =~ $state_pattern ]]; then
                state_prefix="${BASH_REMATCH[1]}"
                state="${BASH_REMATCH[2]}"
                if [[ "$state" == PASS ]]; then color='1;32'; else color='1;31'; fi
                printf '\033[36m%s\033[0mTask state: %s\033[%sm%s\033[0m\n' "$prefix" "$state_prefix" "$color" "$state"
                color=""
                continue
            fi
            case "$message" in
                Agent\ assistant:*|Agent\ user:*|Agent\ stdout:*) color=32 ;;
                Agent\ tool\ *|EXEC\ command:*|EXEC\ stdout:*) color=90 ;;
                EXEC\ stderr:*) color=31 ;;
                Agent\ stderr:*) color=33 ;;
                *)
                    color=""
                    printf '\033[36m%s\033[0m%s\n' "$prefix" "$message"
                    continue
                    ;;
            esac
        fi
        if [[ -n "$color" ]]; then
            printf '\033[%sm%s\033[0m\n' "$color" "$line"
        else
            printf '%s\n' "$line"
        fi
    done
}

if [[ -t 1 && "${TERM:-}" != dumb && -z "${NO_COLOR+x}" ]]; then
    exec > >(tee -a "$log_file" | color_bridge_output) 2>&1
else
    exec > >(tee -a "$log_file") 2>&1
fi
echo "Bridge log: $log_file"

if [[ ! -f "$config_file" ]]; then
    cp -- config.example.json "$config_file" || exit 1
    echo "Created $config_file. Set hub_url, access_key, and agent_command before running." >&2
    exit 1
fi

export PYTHONUNBUFFERED=1
# Windows pipes otherwise inherit the legacy ANSI code page.
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
python_args=(-m cross_zone --config "$config_file" --workspace "$workspace_dir")
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
