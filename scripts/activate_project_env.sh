#!/usr/bin/env bash
# Source this file to enter the FaceSymAi base environment:
#   source scripts/activate_project_env.sh

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
PROJECT_CONDA_ENV="${PROJECT_CONDA_ENV:-anti-spoofing_scc_175}"

export PROJECT_ROOT
export PROJECT_CONDA_ENV
export FACE_SYM_AI_CONDA_ENV="$PROJECT_CONDA_ENV"
export PYTHONNOUSERSITE="${PYTHONNOUSERSITE:-1}"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

conda_base="${CONDA_BASE:-}"
if [ -z "$conda_base" ] && command -v conda >/dev/null 2>&1; then
  conda_base="$(conda info --base 2>/dev/null || true)"
fi
if [ -z "$conda_base" ] && [ -d "/home/scc/anaconda3" ]; then
  conda_base="/home/scc/anaconda3"
fi

if [ -z "$conda_base" ] || [ ! -f "$conda_base/etc/profile.d/conda.sh" ]; then
  echo "Cannot locate conda.sh; expected conda env: $PROJECT_CONDA_ENV" >&2
  return 1 2>/dev/null || exit 1
fi

# shellcheck source=/dev/null
. "$conda_base/etc/profile.d/conda.sh"
conda activate "$PROJECT_CONDA_ENV"
