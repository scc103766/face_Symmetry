#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/supercloud/llm-code/scc/scc}"
OWNER="${SCC_CODEX_OWNER:-scc}"
GROUP="${SCC_CODEX_GROUP:-scc}"
CODEX_HOME="$ROOT/.codex-home"
CODEX_LOCAL="$ROOT/.codex-local"
SESSION_ID="20260603-000000-scc-root-project-isolated-session-pool"
CREATED_AT="2026-06-03T00:00:00+00:00"

mkdir_or_sudo() {
  if mkdir -p "$@" 2>/dev/null; then
    return 0
  fi
  sudo install -d -o "$OWNER" -g "$GROUP" -m 2775 "$@"
}

write_file_or_sudo() {
  local target="$1"
  local mode="${2:-0664}"
  local tmp
  tmp="$(mktemp)"
  cat > "$tmp"
  if install -m "$mode" "$tmp" "$target" 2>/dev/null; then
    rm -f "$tmp"
    return 0
  fi
  sudo install -o "$OWNER" -g "$GROUP" -m "$mode" "$tmp" "$target"
  rm -f "$tmp"
}

mkdir_or_sudo \
  "$CODEX_HOME" \
  "$CODEX_HOME/sessions" \
  "$CODEX_HOME/log" \
  "$CODEX_HOME/tmp" \
  "$CODEX_HOME/shell_snapshots" \
  "$CODEX_HOME/cache" \
  "$CODEX_HOME/memories" \
  "$CODEX_LOCAL" \
  "$CODEX_LOCAL/sessions" \
  "$ROOT/scripts"

touch "$ROOT/.codex" 2>/dev/null || sudo install -o "$OWNER" -g "$GROUP" -m 0664 /dev/null "$ROOT/.codex"
touch "$CODEX_HOME/session_index.jsonl" 2>/dev/null || sudo install -o "$OWNER" -g "$GROUP" -m 0664 /dev/null "$CODEX_HOME/session_index.jsonl"

if [ ! -e "$CODEX_HOME/auth.json" ] && [ -e "$HOME/.codex/auth.json" ]; then
  ln -s "$HOME/.codex/auth.json" "$CODEX_HOME/auth.json" 2>/dev/null || sudo ln -s "$HOME/.codex/auth.json" "$CODEX_HOME/auth.json"
fi

for filename in installation_id models_cache.json version.json; do
  if [ ! -e "$CODEX_HOME/$filename" ] && [ -e "$HOME/.codex/$filename" ]; then
    cp -p "$HOME/.codex/$filename" "$CODEX_HOME/$filename" 2>/dev/null || sudo install -o "$OWNER" -g "$GROUP" -m 0664 "$HOME/.codex/$filename" "$CODEX_HOME/$filename"
  fi
done

if [ ! -e "$CODEX_HOME/config.toml" ]; then
  write_file_or_sudo "$CODEX_HOME/config.toml" 0664 <<'CONFIG'
model = "gpt-5.5"
model_reasoning_effort = "xhigh"
service_tier = "fast"
personality = "pragmatic"

[projects."/supercloud/llm-code/scc/scc"]
trust_level = "trusted"

[projects."/supercloud/llm-code/scc/scc/FaceSymAi"]
trust_level = "trusted"

[projects."/supercloud/llm-code/scc/scc/Liveness_Detection"]
trust_level = "trusted"

[projects."/supercloud/llm-code/scc/scc/DeepfakeBench"]
trust_level = "trusted"

[projects."/supercloud/llm-code/scc/scc/project_robot"]
trust_level = "trusted"

[tui.model_availability_nux]
"gpt-5.5" = 4
CONFIG
elif ! grep -Fq '[projects."/supercloud/llm-code/scc/scc"]' "$CODEX_HOME/config.toml"; then
  printf '\n[projects."/supercloud/llm-code/scc/scc"]\ntrust_level = "trusted"\n' | sudo tee -a "$CODEX_HOME/config.toml" >/dev/null
fi

if [ ! -e "$CODEX_LOCAL/current_session" ]; then
  printf '%s\n' "$SESSION_ID" | write_file_or_sudo "$CODEX_LOCAL/current_session" 0664
fi

if [ ! -e "$CODEX_LOCAL/index.json" ]; then
  write_file_or_sudo "$CODEX_LOCAL/index.json" 0664 <<EOF_INDEX
[
  {
    "id": "$SESSION_ID",
    "title": "scc root project isolated session pool",
    "status": "active",
    "created_at": "$CREATED_AT",
    "updated_at": "$CREATED_AT",
    "branch": null,
    "client": "vscode"
  }
]
EOF_INDEX
fi

if [ ! -e "$CODEX_LOCAL/sessions/$SESSION_ID.json" ]; then
  write_file_or_sudo "$CODEX_LOCAL/sessions/$SESSION_ID.json" 0664 <<EOF_SESSION
{
  "id": "$SESSION_ID",
  "title": "scc root project isolated session pool",
  "status": "active",
  "created_at": "$CREATED_AT",
  "updated_at": "$CREATED_AT",
  "root": "$ROOT",
  "branch": null,
  "commit": null,
  "client": "vscode",
  "vscode": {
    "workspace": "$ROOT",
    "external_ref": "scc root project CODEX_HOME: .codex-home"
  },
  "tags": ["scc-root", "isolated-codex", "vscode"],
  "summary": "Dedicated Codex session pool for /supercloud/llm-code/scc/scc. Native Codex and VS Code extension sessions are directed to .codex-home; lightweight handoff records live in .codex-local.",
  "notes": [],
  "events": [
    {
      "at": "$CREATED_AT",
      "text": "Initialized scc root project-local Codex session pool."
    }
  ],
  "tasks": []
}
EOF_SESSION
fi

if [ ! -e "$ROOT/scripts/codex_scc_root.sh" ]; then
  write_file_or_sudo "$ROOT/scripts/codex_scc_root.sh" 0775 <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
CODEX_BIN="${CODEX_BIN:-/home/scc/.npm-global/bin/codex}"
PROJECT_CONDA_ENV="${PROJECT_CONDA_ENV:-anti-spoofing_scc_175}"

export CODEX_HOME="${CODEX_HOME:-$PROJECT_ROOT/.codex-home}"
export CODEX_PROJECT_ROOT="$PROJECT_ROOT"
export CODEX_PROJECT_NAME="scc-root"
export PROJECT_CONDA_ENV
export PYTHONNOUSERSITE="${PYTHONNOUSERSITE:-1}"

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
mkdir -p "$CODEX_HOME/sessions" "$CODEX_HOME/log" "$CODEX_HOME/tmp" "$CODEX_HOME/shell_snapshots"
if [ ! -e "$CODEX_HOME/auth.json" ] && [ -e "$HOME/.codex/auth.json" ]; then
  ln -s "$HOME/.codex/auth.json" "$CODEX_HOME/auth.json"
fi
if [ ! -e "$CODEX_HOME/session_index.jsonl" ]; then
  touch "$CODEX_HOME/session_index.jsonl"
fi

exec "$CODEX_BIN" --cd "$PROJECT_ROOT" "$@"
WRAPPER
fi

printf 'scc root Codex pool initialized at %s\n' "$ROOT"
