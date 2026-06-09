#!/usr/bin/env python3
"""Copy FaceSymAi native Codex sessions into the project Codex home.

By default this tool copies matching session JSONL files and writes a project
local session_index.jsonl. With --remove-global-index it also removes matching
records from the global index while leaving the original JSONL files in place.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import shutil
from typing import Any


PROJECT_ROOT = pathlib.Path("/supercloud/llm-code/scc/scc/FaceSymAi")


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def write_jsonl(path: pathlib.Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records)
    path.write_text(text, encoding="utf-8")


def session_meta(path: pathlib.Path) -> dict[str, Any] | None:
    for record in read_jsonl(path):
        if record.get("type") == "session_meta":
            payload = record.get("payload")
            return payload if isinstance(payload, dict) else None
    return None


def is_project_cwd(value: Any, project_root: pathlib.Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        cwd = pathlib.Path(value).resolve()
        root = project_root.resolve()
    except OSError:
        return False
    return cwd == root or root in cwd.parents


def indexed_record(
    session_id: str,
    meta: dict[str, Any],
    global_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if session_id in global_index:
        return global_index[session_id]
    return {
        "id": session_id,
        "thread_name": f"FaceSymAi session {session_id[:8]}",
        "updated_at": meta.get("timestamp") or dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--global-home", default=str(pathlib.Path.home() / ".codex"))
    parser.add_argument("--project-home")
    parser.add_argument("--remove-global-index", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project_root = pathlib.Path(args.project_root).resolve()
    global_home = pathlib.Path(args.global_home).expanduser().resolve()
    project_home = (
        pathlib.Path(args.project_home).expanduser().resolve()
        if args.project_home
        else project_root / ".codex-home"
    )
    global_sessions = global_home / "sessions"
    project_sessions = project_home / "sessions"

    global_index_path = global_home / "session_index.jsonl"
    project_index_path = project_home / "session_index.jsonl"
    global_index_records = read_jsonl(global_index_path)
    global_index = {
        record["id"]: record
        for record in global_index_records
        if isinstance(record.get("id"), str)
    }

    matches: list[tuple[pathlib.Path, pathlib.Path, dict[str, Any]]] = []
    for source in sorted(global_sessions.rglob("*.jsonl")):
        meta = session_meta(source)
        if not meta or not is_project_cwd(meta.get("cwd"), project_root):
            continue
        target = project_sessions / source.relative_to(global_sessions)
        matches.append((source, target, meta))

    if not matches:
        print("no FaceSymAi native Codex sessions found in global home")
        return 0

    project_records_by_id = {
        record["id"]: record
        for record in read_jsonl(project_index_path)
        if isinstance(record.get("id"), str)
    }

    matched_ids: set[str] = set()
    for source, target, meta in matches:
        session_id = str(meta.get("id") or source.stem.rsplit("-", 1)[-1])
        matched_ids.add(session_id)
        if session_id in global_index:
            project_records_by_id[session_id] = indexed_record(session_id, meta, global_index)
        elif session_id not in project_records_by_id:
            project_records_by_id[session_id] = indexed_record(session_id, meta, global_index)
        print(f"{source} -> {target}")
        if not args.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    if not args.dry_run:
        write_jsonl(
            project_index_path,
            sorted(
                project_records_by_id.values(),
                key=lambda item: item.get("updated_at", ""),
                reverse=True,
            ),
        )

    if args.remove_global_index:
        kept = [record for record in global_index_records if record.get("id") not in matched_ids]
        removed = len(global_index_records) - len(kept)
        print(f"remove global index records: {removed}")
        if removed and not args.dry_run:
            timestamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
            backup = global_index_path.with_name(
                f"session_index.jsonl.backup-before-facesymai-isolation-{timestamp}"
            )
            shutil.copy2(global_index_path, backup)
            write_jsonl(global_index_path, kept)
            print(f"backup {backup}")

    print(f"migrated sessions: {len(matches)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
