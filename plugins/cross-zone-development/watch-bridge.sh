#!/usr/bin/env bash
set -u

if [[ $# -gt 2 ]]; then
    echo "Usage: $0 [<session-id>|discover] [config-file]" >&2
    exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
session_id="${1:-discover}"
config_file="${2:-config.local.json}"
restart_delay="${BRIDGE_RESTART_DELAY:-3}"

if [[ ! "$restart_delay" =~ ^[0-9]+([.][0-9]+)?$ || ! "$restart_delay" =~ [1-9] ]]; then
    echo "BRIDGE_RESTART_DELAY must be a positive number of seconds." >&2
    exit 2
fi

trap 'echo "Bridge watchdog stopped."; exit 130' INT
trap 'echo "Bridge watchdog stopped."; exit 143' TERM

while true; do
    if [[ "$session_id" == discover ]]; then
        bash "$script_dir/start-bridge.sh" discover "$config_file"
    else
        bash "$script_dir/start-bridge.sh" open "$session_id" "$config_file"
    fi
    bridge_status=$?
    echo "Bridge exited ($bridge_status); restarting in ${restart_delay}s."
    sleep "$restart_delay" || exit $?
done
