#!/usr/bin/env python3
"""Make the installed Codex VS Code extension use project-local CODEX_HOME.

The patch is intentionally narrow: it only sets CODEX_HOME when the active VS
Code workspace belongs to one of the known local projects. Other workspaces keep
using their normal Codex home.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import shutil


KNOWN_PROJECTS = (
    ("FaceSymAi", pathlib.Path("/supercloud/llm-code/scc/scc/FaceSymAi")),
    (
        "Liveness_Detection",
        pathlib.Path("/supercloud/llm-code/scc/scc/Liveness_Detection"),
    ),
    ("project_robot", pathlib.Path("/supercloud/llm-code/scc/scc/project_robot")),
    ("scc-root", pathlib.Path("/supercloud/llm-code/scc/scc")),
)
EXTENSION_ROOT = pathlib.Path(
    "/home/scc/.vscode-server/extensions/openai.chatgpt-26.422.30944-linux-x64"
)
EXTENSION_JS = EXTENSION_ROOT / "out" / "extension.js"
MARKER = "codex-vscode-project-home:start"


def project_specs() -> list[dict[str, str]]:
    return [
        {
            "name": name,
            "root": root.as_posix(),
            "codexHome": (root / ".codex-home").as_posix(),
        }
        for name, root in KNOWN_PROJECTS
    ]


def build_snippet() -> str:
    projects_json = json.dumps(project_specs(), ensure_ascii=False, indent=4)
    return '''
/* codex-vscode-project-home:start */
(() => {
  try {
    const vscode = require("vscode");
    const os = require("os");
    const path = require("path");
    const fs = require("fs");
    const projects = __PROJECTS_JSON__;
    const normalize = (value) => path.resolve(value || "").replace(/[\\\\/]+$/, "");
    const folders = (vscode.workspace.workspaceFolders || [])
      .map((folder) => folder && folder.uri && folder.uri.fsPath)
      .filter(Boolean);
    const isUnderRoot = (folder, projectRoot) => {
      const value = normalize(folder);
      const root = normalize(projectRoot);
      return value === root || value.startsWith(root + path.sep);
    };
    const match = projects.find((project) =>
      folders.some((folder) => isUnderRoot(folder, project.root))
    );

    if (match) {
      for (const dirname of ["sessions", "log", "tmp", "shell_snapshots"]) {
        fs.mkdirSync(path.join(match.codexHome, dirname), { recursive: true });
      }
      const indexPath = path.join(match.codexHome, "session_index.jsonl");
      if (!fs.existsSync(indexPath)) {
        fs.writeFileSync(indexPath, "");
      }
      const globalCodexHome = path.join(os.homedir(), ".codex");
      const ensureFromGlobal = (filename, link) => {
        const source = path.join(globalCodexHome, filename);
        const target = path.join(match.codexHome, filename);
        if (fs.existsSync(target) || !fs.existsSync(source)) {
          return;
        }
        try {
          if (link) {
            fs.symlinkSync(source, target);
          } else {
            fs.copyFileSync(source, target);
          }
        } catch (copyError) {
          if (!link) {
            throw copyError;
          }
          fs.copyFileSync(source, target);
        }
      };
      ensureFromGlobal("auth.json", true);
      for (const filename of [
        "config.toml",
        "installation_id",
        "models_cache.json",
        "version.json",
      ]) {
        ensureFromGlobal(filename, false);
      }
      process.env.CODEX_HOME = match.codexHome;
      process.env.CODEX_PROJECT_ROOT = match.root;
      process.env.CODEX_PROJECT_NAME = match.name;
    }
  } catch (error) {
    console.error(
      "[codex-vscode-project-home]",
      error && error.message ? error.message : error,
    );
  }
})();
/* codex-vscode-project-home:end */
'''.replace("__PROJECTS_JSON__", projects_json)


SNIPPET = build_snippet()


def main() -> int:
    if not EXTENSION_JS.exists():
        raise FileNotFoundError(EXTENSION_JS)

    text = EXTENSION_JS.read_text()
    timestamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    backup = EXTENSION_JS.with_name(
        f"extension.js.backup-before-codex-project-home-{timestamp}"
    )

    start = "/* codex-vscode-project-home:start */"
    end = "/* codex-vscode-project-home:end */"
    if MARKER in text:
        start_index = text.index(start)
        end_index = text.index(end, start_index) + len(end)
        patched = text[:start_index] + SNIPPET.strip() + text[end_index:]
        if patched == text:
            print("extension.js project-home patch already current")
            return 0
        shutil.copy2(EXTENSION_JS, backup)
        EXTENSION_JS.write_text(patched)
        print(f"updated {EXTENSION_JS}")
        print(f"backup {backup}")
        return 0

    prefix = '"use strict";'
    if not text.startswith(prefix):
        raise RuntimeError("unexpected extension.js header")

    shutil.copy2(EXTENSION_JS, backup)
    patched = prefix + SNIPPET + text[len(prefix) :]
    EXTENSION_JS.write_text(patched)
    print(f"patched {EXTENSION_JS}")
    print(f"backup {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
