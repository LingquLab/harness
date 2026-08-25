#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PLUGIN_ROOT="$REPO_ROOT/plugins/superpowers-neo"
TARGET="${CODEX_HOME:-$HOME/.codex}/skills"
DRY_RUN=false

SKILLS=(
  superpowers-neo-designing-complex-changes
  superpowers-neo-writing-plans
  superpowers-neo-using-git-worktrees
  superpowers-neo-executing-plans
  superpowers-neo-validation-strategy
  superpowers-neo-systematic-debugging
  superpowers-neo-code-simplification
  superpowers-neo-requesting-code-review
  superpowers-neo-handling-code-review-feedback
  superpowers-neo-verification-before-completion
  superpowers-neo-git-delivery
)

usage() {
  printf 'Usage: %s [--dry-run] [--target PATH]\n' "$0"
}

while (($#)); do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --target)
      if (($# < 2)); then
        printf 'error: --target requires a path\n' >&2
        exit 2
      fi
      TARGET=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'error: unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

for skill in "${SKILLS[@]}"; do
  source_dir="$PLUGIN_ROOT/skills/$skill"
  target_dir="$TARGET/$skill"

  if [[ ! -f "$source_dir/SKILL.md" || ! -f "$source_dir/agents/openai.yaml" ]]; then
    printf 'error: incomplete source skill: %s\n' "$source_dir" >&2
    exit 1
  fi

  if [[ -e "$target_dir" ]]; then
    printf 'error: target already exists; refusing to overwrite: %s\n' "$target_dir" >&2
    exit 1
  fi
done

if [[ "$DRY_RUN" == true ]]; then
  for skill in "${SKILLS[@]}"; do
    printf 'would install %s -> %s\n' "$PLUGIN_ROOT/skills/$skill" "$TARGET/$skill"
  done
  exit 0
fi

mkdir -p "$TARGET"
LOCK_DIR="$TARGET/.superpowers-neo-install.lock"
if ! mkdir "$LOCK_DIR"; then
  printf 'error: another Superpowers Neo installation may be running: %s\n' "$LOCK_DIR" >&2
  exit 1
fi

STAGE_DIR=""
RESERVED=()

rollback() {
  status=${1:-$?}
  trap - ERR INT TERM
  set +e

  for ((index=${#RESERVED[@]} - 1; index >= 0; index--)); do
    skill=${RESERVED[$index]}
    rm -rf -- "$TARGET/$skill"
  done

  if [[ -n "$STAGE_DIR" && -d "$STAGE_DIR" ]]; then
    rm -rf -- "$STAGE_DIR"
  fi
  rmdir "$LOCK_DIR" 2>/dev/null
  exit "$status"
}

trap 'rollback $?' ERR
trap 'rollback 130' INT
trap 'rollback 143' TERM

STAGE_DIR=$(mktemp -d "$TARGET/.superpowers-neo-stage.XXXXXX")

for skill in "${SKILLS[@]}"; do
  if [[ -e "$TARGET/$skill" ]]; then
    printf 'error: target appeared during installation; refusing to overwrite: %s\n' "$TARGET/$skill" >&2
    false
  fi
  cp -R "$PLUGIN_ROOT/skills/$skill" "$STAGE_DIR/$skill"
done

for skill in "${SKILLS[@]}"; do
  if ! mkdir "$TARGET/$skill"; then
    printf 'error: target appeared during installation; refusing to overwrite: %s\n' "$TARGET/$skill" >&2
    false
  fi
  RESERVED+=("$skill")
done

for skill in "${SKILLS[@]}"; do
  cp -R "$STAGE_DIR/$skill/." "$TARGET/$skill"
done

rm -rf -- "$STAGE_DIR"
rmdir "$LOCK_DIR"
trap - ERR INT TERM

for skill in "${SKILLS[@]}"; do
  printf 'installed %s\n' "$TARGET/$skill"
done
