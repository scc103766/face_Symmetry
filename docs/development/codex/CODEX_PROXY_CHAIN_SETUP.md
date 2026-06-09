# Codex 代理链路配置手册

本文档用于让远程服务器上的 Codex / VS Code Codex 扩展通过本地 Clash/mihomo 出网。

按截图中的 Clash 信息，默认本地代理为：

```text
本地 Clash/mihomo 混合代理: 127.0.0.1:7891
```

目标链路：

```text
远程 Codex
  -> 远程 HTTP(S)_PROXY 127.0.0.1:17991
  -> 远程 HTTP CONNECT bridge
  -> 远程 SOCKS 127.0.0.1:17990
  -> VS Code Remote-SSH 的 RemoteForward
  -> 本地 Clash/mihomo 127.0.0.1:7891
  -> 外网
```

`/tmp/codex-ipc/ipc-<uid>.sock` 是 Codex 本机 IPC 控制通道，不是出网代理。代理链路和 IPC 是两件事。

## 端口规划

默认端口如下，可按用户替换：

```text
本地端 Clash/mihomo mixed port: 7891
远程端 SOCKS 入口:              17990
远程端 HTTP bridge:             17991
```

多人共用服务器时建议每人用不同远程端口：

```text
用户 A: 远程 SOCKS 17990, 远程 HTTP bridge 17991
用户 B: 远程 SOCKS 18990, 远程 HTTP bridge 18991
用户 C: 远程 SOCKS 19990, 远程 HTTP bridge 19991
```

下文命令默认使用：

```bash
LOCAL_CLASH_PORT=7891
REMOTE_SOCKS_PORT=17990
REMOTE_HTTP_PORT=17991
```

## 步骤 1：本地端确认 Clash/mihomo

执行位置：本地电脑终端，不是远程服务器。

确认 Clash/mihomo 页面里有以下信息：

```text
系统代理地址: 127.0.0.1:7891
混合代理端口: 7891
```

本地命令检查端口：

```bash
nc -zv 127.0.0.1 7891
```

成功时会看到类似：

```text
Connection to 127.0.0.1 7891 port [tcp/*] succeeded!
```

如果失败，先启动 Clash/mihomo，或在 Clash/mihomo 设置里启用 mixed port / system proxy。

## 步骤 2：本地端配置 VS Code Remote-SSH 反向转发

执行位置：本地电脑。

这一步不需要单独打开 SSH 转发窗口，而是把反向转发写入本地 SSH 配置。之后 VS Code Remote-SSH 连接服务器时，会自动创建转发。

编辑本地 SSH 配置文件：

```text
macOS / Linux: ~/.ssh/config
Windows:       %USERPROFILE%\.ssh\config
```

添加一个专门给 Codex 代理链路使用的 Host：

```sshconfig
Host scc-dev
    HostName <remote-host>
    User <remote-user>

    # 远程 127.0.0.1:17990 -> 本地 Clash/mihomo 127.0.0.1:7891
    RemoteForward 127.0.0.1:17990 127.0.0.1:7891

    ServerAliveInterval 30
    ServerAliveCountMax 3
    ExitOnForwardFailure yes
```

示例：

```sshconfig
Host scc-dev
    HostName 192.168.17.175
    User scc
    RemoteForward 127.0.0.1:17990 127.0.0.1:7891
    ServerAliveInterval 30
    ServerAliveCountMax 3
    ExitOnForwardFailure yes
```

如果 VS Code 没有使用默认 SSH 配置文件，在本地 VS Code 的 `settings.json` 中指定：

```json
{
  "remote.SSH.configFile": "~/.ssh/config"
}
```

然后在本地 VS Code 执行：

```text
Remote-SSH: Connect to Host...
选择 scc-dev
```

说明：

- 必须选择带有 `RemoteForward` 的 Host，例如上面的 `scc-dev`。
- 这个转发只在 VS Code Remote-SSH 连接存活时存在。
- VS Code 的 `Ports / Forwarded Ports` 面板通常是远程端口转到本地，不适合替代这里的 `RemoteForward`。
- 如果 `17990` 被占用，换成自己的远程端口，例如 `18990`。

## 步骤 3：远程端验证 SOCKS 入口

执行位置：远程服务器终端。

```bash
nc -zv 127.0.0.1 17990
```

成功说明远程端已经能连到本地 Clash/mihomo。

继续验证是否能通过该 SOCKS 出网：

```bash
curl -sS -I -m 10 \
  --socks5-hostname 127.0.0.1:17990 \
  https://api.openai.com/v1/models
```

正常会看到：

```text
HTTP/2 401
www-authenticate: Bearer realm="OpenAI API"
```

`401` 是正常结果，表示已经到达 OpenAI API，只是没有带 API token。

## 步骤 4：远程端启动 HTTP CONNECT bridge

执行位置：远程服务器终端。

选择 bridge 脚本。当前项目可用：

```bash
export CODEX_BRIDGE_SCRIPT=/supercloud/llm-code/scc/scc/Liveness_Detection/tools/codex_socks_http_bridge.py
```

如果该文件不存在，也可以使用 VS Code Codex 扩展自带脚本：

```bash
export CODEX_BRIDGE_SCRIPT=$(ls /home/$USER/.vscode-server/extensions/openai.chatgpt-*/out/codex_socks_http_bridge.py | tail -n 1)
```

确认依赖：

```bash
python3 -m pip show PySocks
```

如果缺少 PySocks：

```bash
python3 -m pip install PySocks
```

启动 bridge：

```bash
mkdir -p "$HOME/.cache/codex-proxy"

nohup python3 "$CODEX_BRIDGE_SCRIPT" \
  --listen-host 127.0.0.1 \
  --listen-port 17991 \
  --socks-host 127.0.0.1 \
  --socks-port 17990 \
  > "$HOME/.cache/codex-proxy/bridge-17991.log" 2>&1 &

echo $! > "$HOME/.cache/codex-proxy/bridge-17991.pid"
```

检查 bridge：

```bash
nc -zv 127.0.0.1 17991
lsof -nP -iTCP:17991
```

## 步骤 5：远程端设置 Codex 代理环境变量

执行位置：远程服务器终端。

当前 shell 临时生效：

```bash
export HTTP_PROXY=http://127.0.0.1:17991
export HTTPS_PROXY=http://127.0.0.1:17991
export http_proxy=$HTTP_PROXY
export https_proxy=$HTTPS_PROXY

export ALL_PROXY=socks5h://127.0.0.1:17990
export all_proxy=$ALL_PROXY

export NO_PROXY=localhost,127.0.0.1,::1
export no_proxy=$NO_PROXY
```

注意：

- `HTTPS_PROXY` 也写 `http://127.0.0.1:17991`。
- 不要写成 `https://127.0.0.1:17991`。
- HTTPS 是通过 HTTP proxy 的 `CONNECT` 隧道转发。

验证 HTTP bridge 到 OpenAI：

```bash
curl -sS -I -m 10 \
  -x http://127.0.0.1:17991 \
  https://api.openai.com/v1/models
```

正常会看到：

```text
HTTP/1.1 200 Connection Established
HTTP/2 401
```

## 步骤 6：远程端启动 Codex CLI

执行位置：远程服务器终端，且必须在步骤 5 的同一个 shell 中执行。

```bash
cd /supercloud/llm-code/scc/scc/FaceSymAi
codex
```

或一次性带代理变量启动：

```bash
cd /supercloud/llm-code/scc/scc/FaceSymAi

HTTP_PROXY=http://127.0.0.1:17991 \
HTTPS_PROXY=http://127.0.0.1:17991 \
ALL_PROXY=socks5h://127.0.0.1:17990 \
NO_PROXY=localhost,127.0.0.1,::1 \
codex
```

## 步骤 7：让 VS Code Codex 扩展生效

执行位置：远程服务器终端。

把代理变量写入远程用户的 shell 配置：

```bash
cat >> ~/.bashrc <<'EOF'

# Codex proxy chain
export HTTP_PROXY=http://127.0.0.1:17991
export HTTPS_PROXY=http://127.0.0.1:17991
export http_proxy=$HTTP_PROXY
export https_proxy=$HTTPS_PROXY
export ALL_PROXY=socks5h://127.0.0.1:17990
export all_proxy=$ALL_PROXY
export NO_PROXY=localhost,127.0.0.1,::1
export no_proxy=$NO_PROXY
EOF
```

执行位置：本地 VS Code。

1. 关闭当前 Remote SSH 窗口。
2. 打开命令面板。
3. 执行 `Remote-SSH: Kill VS Code Server on Host...`。
4. 选择对应远程服务器。
5. 重新连接远程服务器。

重新连接后，VS Code extension host 才会继承新的代理变量。

## 步骤 8：检查 Codex 是否走代理

执行位置：远程服务器终端。

查看 Codex 到 bridge 的连接：

```bash
lsof -nP -iTCP:17991 -iTCP:17990 | rg 'codex|node|python'
```

典型结果：

```text
codex  -> 127.0.0.1:17991
python -> 127.0.0.1:17991 LISTEN
python -> 127.0.0.1:17990
```

查看 Codex IPC：

```bash
ls -la /tmp/codex-ipc
lsof -nP -U | rg '/tmp/codex-ipc'
```

IPC 只说明 Codex 本机控制通道是否存在，不代表代理是否生效。

## 换端口模板

如果当前用户要改成：

```text
本地 Clash:      127.0.0.1:7891
远程 SOCKS:      18990
远程 HTTP bridge:18991
```

本地端 `~/.ssh/config` 中的 `RemoteForward` 改为：

```sshconfig
Host scc-dev
    HostName <remote-host>
    User <remote-user>
    RemoteForward 127.0.0.1:18990 127.0.0.1:7891
    ServerAliveInterval 30
    ServerAliveCountMax 3
    ExitOnForwardFailure yes
```

修改后在本地 VS Code 重新连接该 Host。

远程端 bridge 命令改为：

```bash
nohup python3 "$CODEX_BRIDGE_SCRIPT" \
  --listen-host 127.0.0.1 \
  --listen-port 18991 \
  --socks-host 127.0.0.1 \
  --socks-port 18990 \
  > "$HOME/.cache/codex-proxy/bridge-18991.log" 2>&1 &
```

远程端环境变量改为：

```bash
export HTTP_PROXY=http://127.0.0.1:18991
export HTTPS_PROXY=http://127.0.0.1:18991
export ALL_PROXY=socks5h://127.0.0.1:18990
```

## 常见问题

### 远程端 `17990` 不通

检查本地端是否满足以下条件：

- Clash/mihomo 正在运行，且 `127.0.0.1:7891` 可连接。
- 本地 `~/.ssh/config` 的 Host 中有 `RemoteForward 127.0.0.1:17990 127.0.0.1:7891`。
- 本地 VS Code 连接的是这个带 `RemoteForward` 的 Host。

然后在本地 VS Code 执行：

```text
Remote-SSH: Kill VS Code Server on Host...
```

重新连接远程服务器后，再在远程端检查：

```bash
nc -zv 127.0.0.1 17990
```

### 远程端 `17991` 不通

bridge 没启动或端口被占用：

```bash
lsof -nP -iTCP:17991
tail -n 100 "$HOME/.cache/codex-proxy/bridge-17991.log"
```

### OpenAI 返回 401

这是正常连通性结果，说明代理链路已到达 OpenAI API。

### OpenAI 返回 403 或 Cloudflare 页面

链路是通的，但出口 IP 被限制。切换 Clash/mihomo 节点后重试。

### Codex 仍然不走代理

重启 Codex CLI，或在本地 VS Code 执行：

```text
Remote-SSH: Kill VS Code Server on Host...
```

然后重新连接远程服务器。
