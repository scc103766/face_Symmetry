# 网络代理架构文档

> 配置位置：`~/.bashrc`（第 5-156 行）
> 创建日期：2026-06-11

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────┐
│  本机 (scc@aeye-175)                                    │
│                                                         │
│  HTTP 客户端 (curl/wget/pip/git)                        │
│       │                                                 │
│       ▼                                                 │
│  17991 (HTTP 代理, Codex 管理)                           │
│       │                                                 │
│       ▼                                                 │
│  17992 (SOCKS5 代理, VS Code SSH 隧道)                   │
│       │                                                 │
│       ▼                                                 │
│  VS Code Remote SSH → 本地 Clash 代理 → 互联网          │
└─────────────────────────────────────────────────────────┘
```

**双端口链路**：
- **17991**：HTTP 代理，Codex 扩展自动启动的 Python HTTP bridge
- **17992**：SOCKS5 代理，VS Code Remote SSH 建立的隧道端口

---

## 2. 代理变量

| 变量 | 值 | 说明 |
|------|-----|------|
| `HTTP_PROXY` / `http_proxy` | `http://127.0.0.1:17991` | HTTP 请求走 17991 |
| `HTTPS_PROXY` / `https_proxy` | `http://127.0.0.1:17991` | HTTPS 请求走 17991 |
| `ALL_PROXY` / `all_proxy` | `socks5h://127.0.0.1:17992` | 其他协议走 SOCKS5（如 git SSH） |
| `NO_PROXY` / `no_proxy` | 见下方 | 白名单，直连不走代理 |

**NO_PROXY 白名单**（以下域名直连，不走 VPN）：

```
localhost, 127.0.0.1, ::1              ← 本机服务
api.deepseek.com                         ← PM Agent (Hermes) 调用 DeepSeek API
pypi.tuna.tsinghua.edu.cn               ← Python 包镜像
mirrors.tuna.tsinghua.edu.cn            ← 通用镜像
pypi.org, files.pythonhosted.org        ← PyPI 官方
```

---

## 3. Shell 命令

### `vpn` — 开启/验证代理

```bash
vpn                # 开启代理变量 + 显示链路状态 + 验证网络
vpn <command>      # 代理环境下执行单条命令（不影响当前 shell）
```

**`vpn` 无参数**：先调用 `_scc_vpn_enable_env` 设置代理变量，再调用 `_scc_vpn_chain` 显示端口状态，最后调用 `_scc_vpn_validate_network` 验证 3 个目标站点可达。

**`vpn <cmd>`**：检查两个端口可用后，以内联环境变量的方式执行命令。命令结束后不影响当前 shell 的代理状态。

```bash
vpn curl https://api.openai.com/v1/models   # 仅这条命令走代理
vpn pip install some-package                 # 仅这次 pip 走代理
```

### `unvpn` — 关闭代理

```bash
unvpn              # 清空所有代理变量，恢复本机网络
```

### 网络验证目标

`vpn` 启动时自动验证 3 个站点：

| 目标 | 用途 |
|------|------|
| `https://example.com/` | 通用网络连通性 |
| `https://api.openai.com/` | OpenAI API（Codex 调用） |
| `https://chatgpt.com/` | ChatGPT Web |

---

## 4. Python 包镜像

所有 `pip` / `uv` 安装走清华镜像，不消耗 VPN 流量：

```bash
export PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
export UV_DEFAULT_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"
export UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
export UV_HTTP_TIMEOUT="120"
export UV_HTTP_RETRIES="8"
```

---

## 5. 默认行为

- Shell 启动时 **自动开启 VPN**（第 24-31 行 export），并执行链路检查（第 164-165 行）。
- 两个代理端口必须由 `scc` 用户监听，否则 `_scc_vpn_ports_ready()` 返回失败。
- 端口状态用 `ss -H -ltnpe` 检查，按 UID 过滤，不信任其他用户进程。

---

## 6. bashrc 修改清单

| 行号 | 内容 | 说明 |
|:---:|------|------|
| 5-31 | 代理架构注释 + 所有代理变量 export | 核心配置 |
| 33-38 | PIP_INDEX_URL / UV_* 变量 | Python 包镜像 |
| 40-49 | `_scc_vpn_enable_env()` | 设置代理变量的函数 |
| 51-78 | `vpn()` | 代理开关命令 |
| 80-92 | `_scc_port_state()` / `_scc_vpn_ports_ready()` | 端口检测 |
| 94-103 | `_scc_vpn_chain()` | 链路状态显示 |
| 105-148 | `_scc_vpn_validate_network()` | 3 站点网络验证 |
| 150-156 | `unvpn()` | 关闭代理命令 |
| 164-165 | 启动时自动执行链路检查 | 每次登录可见状态 |

---

## 7. 常见操作

```bash
# 查看当前代理状态
vpn

# 临时关闭代理
unvpn

# 恢复代理
vpn

# 仅某条命令走代理
vpn git clone https://github.com/xxx/yyy.git

# 确认端口状态
ss -H -ltnpe 'sport = :17991 or sport = :17992'
```
