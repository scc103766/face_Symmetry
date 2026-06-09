# FaceSymAi 基础环境

## Conda 环境

项目基础环境固定为：

```bash
anti-spoofing_scc_175
```

验证命令：

```bash
conda run -n anti-spoofing_scc_175 python --version
```

当前验证结果：

```text
Python 3.9.25
```

## 使用方式

进入项目环境：

```bash
source scripts/activate_project_env.sh
```

不改变当前 shell，直接在项目环境中执行命令：

```bash
scripts/run_in_project_env.sh python --version
scripts/run_in_project_env.sh pytest
```

启动项目隔离的 Codex：

```bash
scripts/codex_facesymai.sh
```

该入口会同时设置：

- `CODEX_HOME=/supercloud/llm-code/scc/scc/FaceSymAi/.codex-home`
- `PROJECT_CONDA_ENV=anti-spoofing_scc_175`
- `FACE_SYM_AI_CONDA_ENV=anti-spoofing_scc_175`
- `PYTHONNOUSERSITE=1`
- `PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi/src:$PYTHONPATH`

## 约束

- Python 命令默认使用 `anti-spoofing_scc_175`。
- 新脚本应优先通过 `scripts/run_in_project_env.sh` 或激活脚本运行。
- 不要把环境导出的缓存、模型、日志、`.codex-home`、`.codex-local` 提交到版本控制。
