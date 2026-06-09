# FaceSymAi Codex Session Pool

FaceSymAi uses a project-local Codex setup so sessions for this project do not
mix with other projects.

Storage layout:

```text
.codex                         # empty anchor file
.codex-local/index.json         # local handoff/session manager index
.codex-local/current_session
.codex-local/sessions/*.json
.codex-home/session_index.jsonl # native Codex/VS Code session index
.codex-home/sessions/**/*.jsonl
scripts/codex_session.py
scripts/codex_facesymai.sh
```

Use the project-scoped CLI:

```bash
./scripts/codex_facesymai.sh
```

Manage the lightweight project session pool:

```bash
python3 scripts/codex_session.py list
python3 scripts/codex_session.py show -v
python3 scripts/codex_session.py note "..."
python3 scripts/codex_session.py export -o handoff.md
```

VS Code extension isolation:

```bash
python3 tools/patch_codex_vscode_project_home.py
```

The patch sets `CODEX_HOME` to a project-local `.codex-home` when the active VS
Code workspace belongs to one of the known Codex projects:

- `/supercloud/llm-code/scc/scc/FaceSymAi`
- `/supercloud/llm-code/scc/scc/Liveness_Detection`
- `/supercloud/llm-code/scc/scc/project_robot`

Other workspaces keep using their normal Codex home. Reload the VS Code window
after applying the patch.

Move existing native Codex records for FaceSymAi into the project Codex home:

```bash
python3 tools/migrate_codex_project_sessions.py --remove-global-index
```

The migration copies JSONL session files into `.codex-home/sessions` and removes
only the matching records from the global `~/.codex/session_index.jsonl`.
