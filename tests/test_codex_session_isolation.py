from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


codex_session = load_module("codex_session_under_test", "scripts/codex_session.py")
migrate_sessions = load_module(
    "migrate_codex_project_sessions_under_test",
    "tools/migrate_codex_project_sessions.py",
)
patch_vscode = load_module(
    "patch_codex_vscode_project_home_under_test",
    "tools/patch_codex_vscode_project_home.py",
)


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def make_project(root: Path) -> Path:
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".codex").write_text("", encoding="utf-8")
    workdir = root / "src"
    workdir.mkdir()
    return workdir


def test_store_uses_codex_local_when_codex_is_anchor_file(tmp_path: Path) -> None:
    (tmp_path / ".codex").write_text("", encoding="utf-8")
    store = codex_session.Store(tmp_path)

    assert store.codex_dir == tmp_path / ".codex-local"

    session = {
        "id": "session-1",
        "title": "project handoff",
        "status": "active",
        "created_at": "2026-05-20T00:00:00+00:00",
        "updated_at": "2026-05-20T00:00:00+00:00",
        "branch": "main",
        "client": "cli",
    }

    store.ensure()
    store.save(session)
    store.set_current(session["id"])

    assert (tmp_path / ".codex-local" / "sessions" / "session-1.json").exists()
    assert store.current_id() == "session-1"
    assert (
        read_json(tmp_path / ".codex-local" / "index.json")[0]["id"] == "session-1"
    )

    assert store.delete("session-1") is True
    assert store.current_id() is None
    assert read_json(tmp_path / ".codex-local" / "index.json") == []


def test_cli_switching_projects_keeps_current_sessions_isolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_a = tmp_path / "ProjectA"
    project_b = tmp_path / "ProjectB"
    workdir_a = make_project(project_a)
    workdir_b = make_project(project_b)

    monkeypatch.chdir(workdir_a)
    assert (
        codex_session.main(["start", "alpha session", "--summary", "project A"]) == 0
    )
    session_a = capsys.readouterr().out.strip().removeprefix("started: ")
    assert codex_session.main(["note", "note belongs to project A"]) == 0
    capsys.readouterr()

    monkeypatch.chdir(workdir_b)
    assert (
        codex_session.main(["start", "beta session", "--summary", "project B"]) == 0
    )
    session_b = capsys.readouterr().out.strip().removeprefix("started: ")
    assert session_b != session_a
    assert codex_session.main(["note", "note belongs to project B"]) == 0
    capsys.readouterr()

    with pytest.raises(SystemExit, match=f"session not found: {session_a}"):
        codex_session.main(["show", session_a])

    monkeypatch.chdir(workdir_a)
    assert codex_session.main(["list"]) == 0
    project_a_list = capsys.readouterr().out

    assert session_a in project_a_list
    assert session_b not in project_a_list
    assert (project_a / ".codex-local" / "current_session").read_text(
        encoding="utf-8"
    ).strip() == session_a
    assert (project_b / ".codex-local" / "current_session").read_text(
        encoding="utf-8"
    ).strip() == session_b

    session_file_a = project_a / ".codex-local" / "sessions" / f"{session_a}.json"
    session_file_b = project_b / ".codex-local" / "sessions" / f"{session_b}.json"
    assert session_file_a.exists()
    assert session_file_b.exists()
    assert not (
        project_a / ".codex-local" / "sessions" / f"{session_b}.json"
    ).exists()
    assert not (
        project_b / ".codex-local" / "sessions" / f"{session_a}.json"
    ).exists()

    saved_a = read_json(session_file_a)
    saved_b = read_json(session_file_b)
    assert saved_a["root"] == str(project_a)
    assert saved_b["root"] == str(project_b)
    assert [note["text"] for note in saved_a["notes"]] == [
        "note belongs to project A"
    ]
    assert [note["text"] for note in saved_b["notes"]] == [
        "note belongs to project B"
    ]
    assert [
        item["id"] for item in read_json(project_a / ".codex-local" / "index.json")
    ] == [session_a]
    assert [
        item["id"] for item in read_json(project_b / ".codex-local" / "index.json")
    ] == [session_b]


def test_native_session_parse_and_mapping_preserve_vscode_metadata(tmp_path: Path) -> None:
    native_id = "019e3a51-9c17-77f2-bce9-ef7fbc5a6d72"
    session_file = tmp_path / "2026" / "05" / "20" / f"rollout-{native_id}.jsonl"
    workspace = tmp_path / "FaceSymAi"
    write_jsonl(
        session_file,
        [
            {
                "type": "session_meta",
                "timestamp": "2026-05-20T01:00:00Z",
                "payload": {
                    "id": native_id,
                    "cwd": str(workspace),
                    "source": "vscode-extension",
                    "originator": "vscode",
                    "cli_version": "0.130.0",
                    "model_provider": "openai",
                    "git": {"repository_url": "https://example.test/facesymai.git"},
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-05-20T01:05:00Z",
                "payload": {"text": "done"},
            },
        ],
    )
    indexed = {
        native_id: {
            "id": native_id,
            "thread_name": "FaceSymAi isolation]",
            "updated_at": "2026-05-20T01:06:00Z",
        }
    }

    native = codex_session.parse_native_session(session_file, indexed)

    assert native["native_id"] == native_id
    assert native["title"] == "FaceSymAi isolation"
    assert native["client"] == "vscode"
    assert native["cwd"] == str(workspace)
    assert native["line_count"] == 2
    assert native["item_counts"] == {"session_meta": 1, "response_item": 1}

    mapped = codex_session.session_from_native(workspace, native)

    assert mapped["id"] == f"native-{native_id}"
    assert mapped["root"] == str(workspace)
    assert mapped["client"] == "vscode"
    assert mapped["vscode"] == {
        "workspace": str(workspace),
        "external_ref": f"native:{native_id}",
    }
    assert mapped["native_codex"]["session_id"] == native_id
    assert (
        mapped["native_codex"]["repository_url"]
        == "https://example.test/facesymai.git"
    )
    assert mapped["tags"] == ["native-codex", "vscode"]


def test_native_session_files_support_date_filter(tmp_path: Path) -> None:
    dated = tmp_path / "2026" / "05" / "20" / "session-a.jsonl"
    other = tmp_path / "2026" / "05" / "21" / "session-b.jsonl"
    dated.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    dated.write_text("{}", encoding="utf-8")
    other.write_text("{}", encoding="utf-8")

    assert codex_session.native_session_files(tmp_path, "2026-5-20") == [dated]
    assert codex_session.native_session_files(tmp_path, None) == [dated, other]

    with pytest.raises(SystemExit, match="--date must look like"):
        codex_session.native_session_files(tmp_path, "2026-05")


def test_migration_copies_only_project_sessions_and_cleans_global_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "FaceSymAi"
    project_root.mkdir()
    global_home = tmp_path / "global-codex"
    project_home = tmp_path / "project-codex-home"
    global_sessions = global_home / "sessions"
    matching_session = global_sessions / "2026" / "05" / "20" / "rollout-match-1.jsonl"
    sibling_session = (
        global_sessions / "2026" / "05" / "20" / "rollout-sibling-1.jsonl"
    )
    other_session = global_sessions / "2026" / "05" / "20" / "rollout-other-1.jsonl"

    write_jsonl(
        matching_session,
        [
            {
                "type": "session_meta",
                "payload": {
                    "id": "match-1",
                    "cwd": str(project_root / "subdir"),
                    "timestamp": "2026-05-20T02:00:00Z",
                },
            }
        ],
    )
    write_jsonl(
        sibling_session,
        [
            {
                "type": "session_meta",
                "payload": {
                    "id": "sibling-1",
                    "cwd": str(tmp_path / "FaceSymAi-copy"),
                    "timestamp": "2026-05-20T02:30:00Z",
                },
            }
        ],
    )
    write_jsonl(
        other_session,
        [
            {
                "type": "session_meta",
                "payload": {
                    "id": "other-1",
                    "cwd": str(tmp_path / "OtherProject"),
                    "timestamp": "2026-05-20T02:00:00Z",
                },
            }
        ],
    )
    write_jsonl(
        global_home / "session_index.jsonl",
        [
            {
                "id": "match-1",
                "thread_name": "FaceSymAi",
                "updated_at": "2026-05-20T02:00:00Z",
            },
            {
                "id": "other-1",
                "thread_name": "Other",
                "updated_at": "2026-05-20T03:00:00Z",
            },
            {
                "id": "sibling-1",
                "thread_name": "Sibling",
                "updated_at": "2026-05-20T02:30:00Z",
            },
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "migrate_codex_project_sessions.py",
            "--project-root",
            str(project_root),
            "--global-home",
            str(global_home),
            "--project-home",
            str(project_home),
            "--remove-global-index",
        ],
    )

    assert migrate_sessions.main() == 0

    copied = project_home / "sessions" / matching_session.relative_to(global_sessions)
    assert copied.exists()
    assert not (
        project_home / "sessions" / sibling_session.relative_to(global_sessions)
    ).exists()
    assert not (
        project_home / "sessions" / other_session.relative_to(global_sessions)
    ).exists()

    project_index = migrate_sessions.read_jsonl(project_home / "session_index.jsonl")
    assert [record["id"] for record in project_index] == ["match-1"]

    global_index = migrate_sessions.read_jsonl(global_home / "session_index.jsonl")
    assert [record["id"] for record in global_index] == ["other-1", "sibling-1"]
    assert list(
        global_home.glob("session_index.jsonl.backup-before-facesymai-isolation-*")
    )


def test_vscode_project_home_patch_is_scoped_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extension_js = tmp_path / "extension.js"
    extension_js.write_text('"use strict";\nconsole.log("extension");\n', encoding="utf-8")
    monkeypatch.setattr(patch_vscode, "EXTENSION_JS", extension_js)

    assert patch_vscode.main() == 0

    patched = extension_js.read_text(encoding="utf-8")
    assert patched.startswith('"use strict";\n/* codex-vscode-project-home:start */')
    assert '"root": "/supercloud/llm-code/scc/scc/FaceSymAi"' in patched
    assert '"root": "/supercloud/llm-code/scc/scc/Liveness_Detection"' in patched
    assert '"root": "/supercloud/llm-code/scc/scc/project_robot"' in patched
    assert 'process.env.CODEX_HOME = match.codexHome;' in patched
    assert 'process.env.CODEX_PROJECT_NAME = match.name;' in patched
    assert 'path.join(match.codexHome, "session_index.jsonl")' in patched
    assert 'ensureFromGlobal("auth.json", true);' in patched
    assert '"config.toml"' in patched
    assert 'replace(/[\\\\/]+$/, "")' in patched
    assert 'value === root || value.startsWith(root + path.sep)' in patched
    backups = list(tmp_path.glob("extension.js.backup-before-codex-project-home-*"))
    assert len(backups) == 1

    assert patch_vscode.main() == 0

    assert extension_js.read_text(encoding="utf-8") == patched
    assert (
        len(list(tmp_path.glob("extension.js.backup-before-codex-project-home-*")))
        == 1
    )
