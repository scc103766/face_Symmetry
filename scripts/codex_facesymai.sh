#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
CODEX_BIN="${CODEX_BIN:-/home/scc/.npm-global/bin/codex}"
PROJECT_CONDA_ENV="${PROJECT_CONDA_ENV:-anti-spoofing_scc_175}"

export CODEX_HOME="${CODEX_HOME:-$PROJECT_ROOT/.codex-home}"
export CODEX_PROJECT_ROOT="$PROJECT_ROOT"
export PROJECT_CONDA_ENV
export FACE_SYM_AI_CONDA_ENV="$PROJECT_CONDA_ENV"
export PYTHONNOUSERSITE="${PYTHONNOUSERSITE:-1}"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

activate_project_conda() {
  if [ "${CONDA_DEFAULT_ENV:-}" = "$PROJECT_CONDA_ENV" ]; then
    return 0
  fi

  local conda_base="${CONDA_BASE:-}"
  if [ -z "$conda_base" ] && command -v conda >/dev/null 2>&1; then
    conda_base="$(conda info --base 2>/dev/null || true)"
  fi
  if [ -z "$conda_base" ] && [ -d "/home/scc/anaconda3" ]; then
    conda_base="/home/scc/anaconda3"
  fi

  if [ -z "$conda_base" ] || [ ! -f "$conda_base/etc/profile.d/conda.sh" ]; then
    echo "Cannot locate conda.sh; expected conda env: $PROJECT_CONDA_ENV" >&2
    exit 1
  fi

  # shellcheck source=/dev/null
  . "$conda_base/etc/profile.d/conda.sh"
  conda activate "$PROJECT_CONDA_ENV"
}

activate_project_conda

mkdir -p \
  "$CODEX_HOME/sessions" \
  "$CODEX_HOME/log" \
  "$CODEX_HOME/tmp" \
  "$CODEX_HOME/shell_snapshots"

if [ ! -e "$CODEX_HOME/auth.json" ] && [ -e "$HOME/.codex/auth.json" ]; then
  ln -s "$HOME/.codex/auth.json" "$CODEX_HOME/auth.json"
fi

if [ ! -e "$CODEX_HOME/config.toml" ] && [ -e "$HOME/.codex/config.toml" ]; then
  cp -p "$HOME/.codex/config.toml" "$CODEX_HOME/config.toml"
fi

if [ ! -e "$CODEX_HOME/installation_id" ] && [ -e "$HOME/.codex/installation_id" ]; then
  cp -p "$HOME/.codex/installation_id" "$CODEX_HOME/installation_id"
fi

if [ ! -e "$CODEX_HOME/models_cache.json" ] && [ -e "$HOME/.codex/models_cache.json" ]; then
  cp -p "$HOME/.codex/models_cache.json" "$CODEX_HOME/models_cache.json"
fi

if [ ! -e "$CODEX_HOME/version.json" ] && [ -e "$HOME/.codex/version.json" ]; then
  cp -p "$HOME/.codex/version.json" "$CODEX_HOME/version.json"
fi

if [ ! -e "$CODEX_HOME/session_index.jsonl" ]; then
  touch "$CODEX_HOME/session_index.jsonl"
fi

exec "$CODEX_BIN" --cd "$PROJECT_ROOT" "$@"
