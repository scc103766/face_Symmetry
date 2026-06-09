#!/usr/bin/env python3
"""
Local Codex session manager.

This tool keeps lightweight session state under .codex/sessions so work can be
resumed, summarized, and handed off without depending on any remote service.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


APP_DIR = ".codex"
FALLBACK_APP_DIR = ".codex-local"
SESSIONS_DIR = "sessions"
CURRENT_FILE = "current_session"
INDEX_FILE = "index.json"
NATIVE_CODEX_DIR = Path.home() / ".codex"
NATIVE_SESSION_INDEX = NATIVE_CODEX_DIR / "session_index.jsonl"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def repo_root(start: Path) -> Path:
    cur = start.resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / ".git").exists():
            return candidate
    return cur


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "session"


def clean_title(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    value = re.sub(r"[】\]\}]+$", "", value).strip()
    return value


def run_git(root: Path, args: List[str]) -> Optional[str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(root),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def normalize_native_date(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    value = value.strip().replace("-", "/")
    parts = [part for part in value.split("/") if part]
    if len(parts) != 3:
        raise SystemExit("--date must look like YYYY-MM-DD or YYYY/MM/DD")
    year, month, day = parts
    return Path(year) / month.zfill(2) / day.zfill(2)


def load_native_index(index_path: Path = NATIVE_SESSION_INDEX) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for record in read_jsonl(index_path):
        session_id = record.get("id")
        if session_id:
            indexed[session_id] = record
    return indexed


def native_session_files(base: Path, date_value: Optional[str]) -> List[Path]:
    date_path = normalize_native_date(date_value)
    search_root = base / date_path if date_path else base
    if not search_root.exists():
        return []
    return sorted(search_root.rglob("*.jsonl"))


def parse_native_session(path: Path, indexed: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    first_timestamp: Optional[str] = None
    last_timestamp: Optional[str] = None
    line_count = 0
    item_counts: Dict[str, int] = {}

    for record in read_jsonl(path):
        line_count += 1
        record_type = str(record.get("type") or "unknown")
        item_counts[record_type] = item_counts.get(record_type, 0) + 1
        timestamp = record.get("timestamp")
        if timestamp:
            first_timestamp = first_timestamp or timestamp
            last_timestamp = timestamp
        if record_type == "session_meta":
            meta = record.get("payload") or {}

    native_id = meta.get("id") or path.stem.rsplit("-", 1)[-1]
    index_record = indexed.get(native_id, {})
    thread_name = clean_title(index_record.get("thread_name") or "")
    updated_at = index_record.get("updated_at") or last_timestamp or first_timestamp or utc_now()
    git_meta = meta.get("git") or {}
    source = meta.get("source") or ""
    originator = meta.get("originator") or ""
    client = "vscode" if "vscode" in f"{source} {originator}".lower() else "cli"

    return {
        "native_id": native_id,
        "path": str(path),
        "thread_name": thread_name,
        "title": thread_name or f"Codex native session {native_id[:8]}",
        "created_at": first_timestamp or utc_now(),
        "updated_at": updated_at,
        "cwd": meta.get("cwd"),
        "source": source or None,
        "originator": originator or None,
        "client": client,
        "cli_version": meta.get("cli_version"),
        "model_provider": meta.get("model_provider"),
        "repository_url": git_meta.get("repository_url"),
        "line_count": line_count,
        "item_counts": item_counts,
    }


def session_from_native(root: Path, native: Dict[str, Any]) -> Dict[str, Any]:
    native_id = native["native_id"]
    session_id = f"native-{native_id}"
    client = native.get("client") or "cli"
    workspace = native.get("cwd") if client == "vscode" else None
    return {
        "id": session_id,
        "title": native.get("title") or f"Codex native session {native_id[:8]}",
        "status": "active",
        "created_at": native.get("created_at") or utc_now(),
        "updated_at": native.get("updated_at") or utc_now(),
        "root": native.get("cwd") or str(root),
        "branch": run_git(root, ["branch", "--show-current"]),
        "commit": run_git(root, ["rev-parse", "--short", "HEAD"]),
        "client": client,
        "vscode": {
            "workspace": workspace,
            "external_ref": f"native:{native_id}" if client == "vscode" else None,
        },
        "native_codex": {
            "session_id": native_id,
            "path": native.get("path"),
            "source": native.get("source"),
            "originator": native.get("originator"),
            "cli_version": native.get("cli_version"),
            "model_provider": native.get("model_provider"),
            "thread_name": native.get("thread_name"),
            "updated_at": native.get("updated_at"),
            "repository_url": native.get("repository_url"),
            "line_count": native.get("line_count"),
            "item_counts": native.get("item_counts"),
        },
        "tags": ["native-codex", client],
        "summary": "从 ~/.codex 原生会话导入的本地映射，用于交接、索引和删除管理。",
        "notes": [],
        "events": [
            {
                "at": utc_now(),
                "text": f"导入原生 Codex 会话：{native.get('path')}",
            }
        ],
        "tasks": [],
    }


def remove_native_index_record(native_id: str, index_path: Path = NATIVE_SESSION_INDEX) -> bool:
    if not index_path.exists():
        return False
    lines = index_path.read_text(encoding="utf-8").splitlines()
    kept: List[str] = []
    removed = False
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            kept.append(line)
            continue
        if record.get("id") == native_id:
            removed = True
            continue
        kept.append(line)
    if removed:
        index_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return removed


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        preferred = root / APP_DIR
        self.codex_dir = (
            preferred if not preferred.exists() or preferred.is_dir() else root / FALLBACK_APP_DIR
        )
        self.sessions_dir = self.codex_dir / SESSIONS_DIR
        self.current_path = self.codex_dir / CURRENT_FILE
        self.index_path = self.codex_dir / INDEX_FILE

    def ensure(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self.write_index([])

    def read_index(self) -> List[Dict[str, Any]]:
        self.ensure()
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    def write_index(self, items: List[Dict[str, Any]]) -> None:
        self.index_path.write_text(
            json.dumps(items, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def load(self, session_id: str) -> Dict[str, Any]:
        path = self.session_path(session_id)
        if not path.exists():
            raise SystemExit(f"session not found: {session_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, session: Dict[str, Any]) -> None:
        session["updated_at"] = utc_now()
        self.session_path(session["id"]).write_text(
            json.dumps(session, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.upsert_index(session)

    def upsert_index(self, session: Dict[str, Any]) -> None:
        items = [x for x in self.read_index() if x.get("id") != session["id"]]
        items.append(
            {
                "id": session["id"],
                "title": session["title"],
                "status": session["status"],
                "created_at": session["created_at"],
                "updated_at": session["updated_at"],
                "branch": session.get("branch"),
                "client": session.get("client", "cli"),
            }
        )
        items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        self.write_index(items)

    def set_current(self, session_id: str) -> None:
        self.current_path.write_text(session_id + "\n", encoding="utf-8")

    def current_id(self) -> Optional[str]:
        if not self.current_path.exists():
            return None
        value = self.current_path.read_text(encoding="utf-8").strip()
        return value or None

    def clear_current_if(self, session_id: str) -> None:
        if self.current_id() == session_id and self.current_path.exists():
            self.current_path.unlink()

    def delete(self, session_id: str, missing_ok: bool = False) -> bool:
        path = self.session_path(session_id)
        if not path.exists() and not missing_ok:
            raise SystemExit(f"session not found: {session_id}")

        deleted = False
        if path.exists():
            path.unlink()
            deleted = True

        items = [x for x in self.read_index() if x.get("id") != session_id]
        self.write_index(items)
        self.clear_current_if(session_id)
        return deleted


def current_or_arg(store: Store, session_id: Optional[str]) -> str:
    if session_id:
        return session_id
    current = store.current_id()
    if not current:
        raise SystemExit("no current session; run `codex_session.py start ...` first")
    return current


def new_session(
    root: Path,
    title: str,
    tags: Iterable[str],
    client: str,
    vscode_workspace: Optional[str],
    external_ref: Optional[str],
) -> Dict[str, Any]:
    now = utc_now()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    session_id = f"{stamp}-{slugify(title)}"
    return {
        "id": session_id,
        "title": title,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "root": str(root),
        "branch": run_git(root, ["branch", "--show-current"]),
        "commit": run_git(root, ["rev-parse", "--short", "HEAD"]),
        "client": client,
        "vscode": {
            "workspace": vscode_workspace,
            "external_ref": external_ref,
        },
        "tags": list(tags),
        "summary": "",
        "notes": [],
        "events": [],
        "tasks": [],
    }


def add_entry(session: Dict[str, Any], kind: str, text: str) -> None:
    session[kind].append({"at": utc_now(), "text": text})


def add_task(session: Dict[str, Any], text: str, status: str) -> None:
    next_id = 1 + max([task.get("id", 0) for task in session["tasks"]] or [0])
    session["tasks"].append(
        {"id": next_id, "status": status, "text": text, "created_at": utc_now()}
    )


def update_task(session: Dict[str, Any], task_id: int, status: str) -> None:
    for task in session["tasks"]:
        if task.get("id") == task_id:
            task["status"] = status
            task["updated_at"] = utc_now()
            return
    raise SystemExit(f"task not found: {task_id}")


def print_session(session: Dict[str, Any], verbose: bool = False) -> None:
    print(f"{session['id']}  [{session['status']}] {session['title']}")
    print(f"root: {session.get('root')}")
    print(f"branch: {session.get('branch') or '-'}  commit: {session.get('commit') or '-'}")
    print(f"client: {session.get('client', 'cli')}")
    vscode = session.get("vscode") or {}
    if vscode.get("workspace") or vscode.get("external_ref"):
        print(
            "vscode: "
            f"workspace={vscode.get('workspace') or '-'} "
            f"external_ref={vscode.get('external_ref') or '-'}"
        )
    native = session.get("native_codex") or {}
    if native.get("session_id") or native.get("path"):
        print(
            "native: "
            f"id={native.get('session_id') or '-'} "
            f"path={native.get('path') or '-'}"
        )
        if native.get("source") or native.get("originator"):
            print(
                "native client: "
                f"source={native.get('source') or '-'} "
                f"originator={native.get('originator') or '-'}"
            )
    print(f"created: {session['created_at']}  updated: {session['updated_at']}")
    if session.get("tags"):
        print(f"tags: {', '.join(session['tags'])}")
    if session.get("summary"):
        print(f"\nsummary:\n{session['summary']}")
    if not verbose:
        return
    print_block("tasks", format_tasks(session.get("tasks", [])))
    print_block("notes", [f"- {x['at']} {x['text']}" for x in session.get("notes", [])])
    print_block("events", [f"- {x['at']} {x['text']}" for x in session.get("events", [])])


def print_block(title: str, lines: List[str]) -> None:
    if not lines:
        return
    print(f"\n{title}:")
    for line in lines:
        print(line)


def format_tasks(tasks: List[Dict[str, Any]]) -> List[str]:
    return [f"- #{task['id']} [{task['status']}] {task['text']}" for task in tasks]


def markdown_export(session: Dict[str, Any]) -> str:
    lines = [
        f"# {session['title']}",
        "",
        f"- id: `{session['id']}`",
        f"- status: `{session['status']}`",
        f"- root: `{session.get('root')}`",
        f"- branch: `{session.get('branch') or '-'}`",
        f"- commit: `{session.get('commit') or '-'}`",
        f"- client: `{session.get('client', 'cli')}`",
        f"- created: `{session['created_at']}`",
        f"- updated: `{session['updated_at']}`",
    ]
    vscode = session.get("vscode") or {}
    if vscode.get("workspace") or vscode.get("external_ref"):
        lines.extend(
            [
                f"- vscode workspace: `{vscode.get('workspace') or '-'}`",
                f"- vscode external ref: `{vscode.get('external_ref') or '-'}`",
            ]
        )
    native = session.get("native_codex") or {}
    if native.get("session_id") or native.get("path"):
        lines.extend(
            [
                f"- native codex id: `{native.get('session_id') or '-'}`",
                f"- native codex path: `{native.get('path') or '-'}`",
                f"- native source: `{native.get('source') or '-'}`",
                f"- native originator: `{native.get('originator') or '-'}`",
            ]
        )
    if session.get("tags"):
        lines.append(f"- tags: `{', '.join(session['tags'])}`")
    if session.get("summary"):
        lines.extend(["", "## Summary", "", session["summary"]])
    if session.get("tasks"):
        lines.extend(["", "## Tasks", ""])
        lines.extend(format_tasks(session["tasks"]))
    if session.get("notes"):
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- `{note['at']}` {note['text']}" for note in session["notes"])
    if session.get("events"):
        lines.extend(["", "## Events", ""])
        lines.extend(f"- `{event['at']}` {event['text']}" for event in session["events"])
    lines.append("")
    return "\n".join(lines)


def cmd_init(args: argparse.Namespace) -> None:
    store = Store(repo_root(Path.cwd()))
    store.ensure()
    print(f"initialized: {store.sessions_dir}")


def cmd_start(args: argparse.Namespace) -> None:
    root = repo_root(Path.cwd())
    store = Store(root)
    store.ensure()
    session = new_session(
        root,
        args.title,
        args.tag or [],
        args.client,
        args.vscode_workspace,
        args.external_ref,
    )
    if args.summary:
        session["summary"] = args.summary
    store.save(session)
    store.set_current(session["id"])
    print(f"started: {session['id']}")


def cmd_list(args: argparse.Namespace) -> None:
    store = Store(repo_root(Path.cwd()))
    current = store.current_id()
    items = store.read_index()
    if args.status:
        items = [x for x in items if x.get("status") == args.status]
    for item in items[: args.limit]:
        marker = "*" if item["id"] == current else " "
        print(
            f"{marker} {item['id']} [{item['status']}] "
            f"({item.get('client', 'cli')}) {item['updated_at']} {item['title']}"
        )


def cmd_list_native(args: argparse.Namespace) -> None:
    indexed = load_native_index()
    files = native_session_files(Path(args.path).expanduser(), args.date)
    if args.session_id:
        files = [
            path
            for path in files
            if args.session_id in path.name or args.session_id == parse_native_session(path, indexed)["native_id"]
        ]
    for path in files:
        native = parse_native_session(path, indexed)
        print(
            f"{native['native_id']} ({native.get('client')}) "
            f"{native.get('updated_at')} {native.get('title')}"
        )
        print(f"  path: {native.get('path')}")
        if native.get("source") or native.get("originator"):
            print(
                f"  source: {native.get('source') or '-'} "
                f"originator: {native.get('originator') or '-'}"
            )


def cmd_import_native(args: argparse.Namespace) -> None:
    root = repo_root(Path.cwd())
    store = Store(root)
    store.ensure()
    indexed = load_native_index()
    files = native_session_files(Path(args.path).expanduser(), args.date)
    imported: List[Dict[str, Any]] = []

    for path in files:
        native = parse_native_session(path, indexed)
        if args.session_id and args.session_id not in {native["native_id"], path.name}:
            continue
        session = session_from_native(root, native)
        if store.session_path(session["id"]).exists() and not args.force:
            imported.append(session)
            continue
        store.save(session)
        imported.append(session)

    if not imported:
        print("no native sessions found")
        return

    if args.set_current:
        store.set_current(imported[0]["id"])

    for session in imported:
        native = session.get("native_codex") or {}
        marker = "current " if args.set_current and session["id"] == imported[0]["id"] else ""
        print(
            f"{marker}mapped: {session['id']} -> "
            f"{native.get('session_id')} ({session.get('client')})"
        )
        print(f"  native path: {native.get('path')}")


def cmd_use(args: argparse.Namespace) -> None:
    store = Store(repo_root(Path.cwd()))
    store.load(args.session_id)
    store.set_current(args.session_id)
    print(f"current: {args.session_id}")


def cmd_show(args: argparse.Namespace) -> None:
    store = Store(repo_root(Path.cwd()))
    session = store.load(current_or_arg(store, args.session_id))
    print_session(session, verbose=args.verbose)


def cmd_note(args: argparse.Namespace) -> None:
    store = Store(repo_root(Path.cwd()))
    session = store.load(current_or_arg(store, args.session_id))
    add_entry(session, "notes", args.text)
    store.save(session)
    print(f"noted: {session['id']}")


def cmd_event(args: argparse.Namespace) -> None:
    store = Store(repo_root(Path.cwd()))
    session = store.load(current_or_arg(store, args.session_id))
    add_entry(session, "events", args.text)
    store.save(session)
    print(f"event added: {session['id']}")


def cmd_task(args: argparse.Namespace) -> None:
    store = Store(repo_root(Path.cwd()))
    session = store.load(current_or_arg(store, args.session_id))
    if args.action == "add":
        add_task(session, args.text, args.status)
    else:
        update_task(session, args.id, args.status)
    store.save(session)
    print(f"tasks updated: {session['id']}")


def cmd_summary(args: argparse.Namespace) -> None:
    store = Store(repo_root(Path.cwd()))
    session = store.load(current_or_arg(store, args.session_id))
    session["summary"] = args.text
    store.save(session)
    print(f"summary updated: {session['id']}")


def cmd_attach_vscode(args: argparse.Namespace) -> None:
    store = Store(repo_root(Path.cwd()))
    session = store.load(current_or_arg(store, args.session_id))
    session["client"] = "mixed" if args.keep_cli else "vscode"
    vscode = session.setdefault("vscode", {})
    if args.workspace:
        vscode["workspace"] = args.workspace
    elif not vscode.get("workspace"):
        vscode["workspace"] = str(repo_root(Path.cwd()))
    if args.external_ref:
        vscode["external_ref"] = args.external_ref
    if args.note:
        add_entry(session, "notes", args.note)
    store.save(session)
    print(f"attached vscode: {session['id']}")


def cmd_close(args: argparse.Namespace) -> None:
    store = Store(repo_root(Path.cwd()))
    session = store.load(current_or_arg(store, args.session_id))
    session["status"] = args.status
    if args.summary:
        session["summary"] = args.summary
    store.save(session)
    print(f"{args.status}: {session['id']}")


def cmd_delete(args: argparse.Namespace) -> None:
    store = Store(repo_root(Path.cwd()))
    session_id = current_or_arg(store, args.session_id)
    session_path = store.session_path(session_id)
    if not session_path.exists() and not args.missing_ok:
        raise SystemExit(f"session not found: {session_id}")
    session = store.load(session_id) if session_path.exists() else {}
    native = session.get("native_codex") or {}

    if not args.yes:
        extra = " and linked native ~/.codex files" if args.native else ""
        answer = input(f"delete session {session_id}{extra}? Type 'yes' to confirm: ")
        if answer != "yes":
            raise SystemExit("delete cancelled")

    native_deleted = False
    native_index_cleaned = False
    if args.native:
        native_id = native.get("session_id")
        native_path_value = native.get("path")
        if not native_path_value and not args.missing_ok:
            raise SystemExit(f"session has no linked native Codex file: {session_id}")
        native_path = Path(native_path_value).expanduser() if native_path_value else None
        if native_path and not native_path.exists() and not args.missing_ok:
            raise SystemExit(f"native session file not found: {native_path}")
        if native_path and native_path.exists():
            native_path.unlink()
            native_deleted = True
        if native_id:
            native_index_cleaned = remove_native_index_record(native_id)

    deleted = store.delete(session_id, missing_ok=args.missing_ok)
    if deleted:
        print(f"deleted: {session_id}")
    else:
        print(f"deleted index/current references for missing session: {session_id}")
    if args.native:
        print(f"native file deleted: {'yes' if native_deleted else 'no'}")
        print(f"native index cleaned: {'yes' if native_index_cleaned else 'no'}")


def cmd_export(args: argparse.Namespace) -> None:
    store = Store(repo_root(Path.cwd()))
    session = store.load(current_or_arg(store, args.session_id))
    output = markdown_export(session)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
        print(f"exported: {path}")
    else:
        print(output, end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage local Codex work sessions under .codex/sessions."
    )
    sub = parser.add_subparsers(required=True)

    init_p = sub.add_parser("init", help="create .codex/sessions storage")
    init_p.set_defaults(func=cmd_init)

    start_p = sub.add_parser("start", help="start a new session")
    start_p.add_argument("title")
    start_p.add_argument("--tag", action="append", help="attach a tag")
    start_p.add_argument("--summary", help="initial summary")
    start_p.add_argument("--client", default="cli", choices=["cli", "vscode", "mixed"])
    start_p.add_argument("--vscode-workspace", help="VS Code workspace path or .code-workspace file")
    start_p.add_argument("--external-ref", help="external client conversation/link/reference")
    start_p.set_defaults(func=cmd_start)

    list_p = sub.add_parser("list", help="list sessions")
    list_p.add_argument("--status", choices=["active", "done", "paused", "archived"])
    list_p.add_argument("--limit", type=int, default=20)
    list_p.set_defaults(func=cmd_list)

    native_list_p = sub.add_parser("list-native", help="list native ~/.codex JSONL sessions")
    native_list_p.add_argument(
        "--path",
        default=str(NATIVE_CODEX_DIR / SESSIONS_DIR),
        help="native Codex sessions root, default: ~/.codex/sessions",
    )
    native_list_p.add_argument("--date", help="filter by YYYY-MM-DD or YYYY/MM/DD")
    native_list_p.add_argument("--session-id", help="filter by native session id")
    native_list_p.set_defaults(func=cmd_list_native)

    native_import_p = sub.add_parser(
        "import-native",
        help="import native ~/.codex JSONL sessions as local managed mappings",
    )
    native_import_p.add_argument(
        "--path",
        default=str(NATIVE_CODEX_DIR / SESSIONS_DIR),
        help="native Codex sessions root, default: ~/.codex/sessions",
    )
    native_import_p.add_argument("--date", help="filter by YYYY-MM-DD or YYYY/MM/DD")
    native_import_p.add_argument("--session-id", help="import only one native session id")
    native_import_p.add_argument("--force", action="store_true", help="overwrite existing mapping")
    native_import_p.add_argument("--set-current", action="store_true", help="set first imported mapping current")
    native_import_p.set_defaults(func=cmd_import_native)

    use_p = sub.add_parser("use", help="set current session")
    use_p.add_argument("session_id")
    use_p.set_defaults(func=cmd_use)

    show_p = sub.add_parser("show", help="show a session")
    show_p.add_argument("session_id", nargs="?")
    show_p.add_argument("-v", "--verbose", action="store_true")
    show_p.set_defaults(func=cmd_show)

    note_p = sub.add_parser("note", help="append a note")
    note_p.add_argument("text")
    note_p.add_argument("--session-id")
    note_p.set_defaults(func=cmd_note)

    event_p = sub.add_parser("event", help="append an event")
    event_p.add_argument("text")
    event_p.add_argument("--session-id")
    event_p.set_defaults(func=cmd_event)

    task_p = sub.add_parser("task", help="add or update tasks")
    task_sub = task_p.add_subparsers(required=True)
    task_add = task_sub.add_parser("add")
    task_add.add_argument("text")
    task_add.add_argument("--status", default="todo", choices=["todo", "doing", "done", "blocked"])
    task_add.add_argument("--session-id")
    task_add.set_defaults(func=cmd_task, action="add")
    task_set = task_sub.add_parser("set")
    task_set.add_argument("id", type=int)
    task_set.add_argument("status", choices=["todo", "doing", "done", "blocked"])
    task_set.add_argument("--session-id")
    task_set.set_defaults(func=cmd_task, action="set")

    summary_p = sub.add_parser("summary", help="replace session summary")
    summary_p.add_argument("text")
    summary_p.add_argument("--session-id")
    summary_p.set_defaults(func=cmd_summary)

    vscode_p = sub.add_parser("attach-vscode", help="attach VS Code Codex metadata")
    vscode_p.add_argument("session_id", nargs="?")
    vscode_p.add_argument("--workspace", help="VS Code workspace path or .code-workspace file")
    vscode_p.add_argument("--external-ref", help="VS Code plugin conversation/link/reference")
    vscode_p.add_argument("--keep-cli", action="store_true", help="mark as mixed instead of vscode-only")
    vscode_p.add_argument("--note", help="add a note while attaching")
    vscode_p.set_defaults(func=cmd_attach_vscode)

    close_p = sub.add_parser("close", help="close or pause a session")
    close_p.add_argument("session_id", nargs="?")
    close_p.add_argument("--status", default="done", choices=["done", "paused", "archived"])
    close_p.add_argument("--summary")
    close_p.set_defaults(func=cmd_close)

    delete_p = sub.add_parser("delete", help="delete a session and clean index/current")
    delete_p.add_argument("session_id", nargs="?")
    delete_p.add_argument("-y", "--yes", action="store_true", help="skip confirmation prompt")
    delete_p.add_argument("--missing-ok", action="store_true", help="clean stale references even if file is missing")
    delete_p.add_argument(
        "--native",
        action="store_true",
        help="also delete linked native ~/.codex JSONL file and clean ~/.codex/session_index.jsonl",
    )
    delete_p.set_defaults(func=cmd_delete)

    export_p = sub.add_parser("export", help="export a session as markdown")
    export_p.add_argument("session_id", nargs="?")
    export_p.add_argument("-o", "--output")
    export_p.set_defaults(func=cmd_export)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
