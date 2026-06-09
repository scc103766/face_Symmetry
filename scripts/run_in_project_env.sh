#!/usr/bin/env bash
set -euo pipefail

PROJECT_CONDA_ENV="${PROJECT_CONDA_ENV:-anti-spoofing_scc_175}"
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <command> [args...]" >&2
  exit 2
fi

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export FACE_SYM_AI_TMP_DIR="${FACE_SYM_AI_TMP_DIR:-$PROJECT_ROOT/tmp}"
mkdir -p "$FACE_SYM_AI_TMP_DIR/matplotlib"
export MPLCONFIGDIR="${MPLCONFIGDIR:-$FACE_SYM_AI_TMP_DIR/matplotlib}"
export GLOG_minloglevel="${GLOG_minloglevel:-2}"
export TF_CPP_MIN_LOG_LEVEL="${TF_CPP_MIN_LOG_LEVEL:-2}"

exec conda run --no-capture-output -n "$PROJECT_CONDA_ENV" "$@"
