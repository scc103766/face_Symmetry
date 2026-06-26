# 网络代理方案 — Codex 部署 Prompt

> 将此 prompt 发给 Codex，即可在新机器上自动搭建相同的代理架构。
> Codex 会先扫描可用端口，不占用他人端口，每个用户使用独立端口。

---

## 使用方式

将下面的 prompt 原样发送给 Codex CLI：

```text
请按以下步骤配置我的网络代理环境。执行前先扫描端口，不可占用其他用户的端口。

## 目标架构

HTTP 客户端 -> 本地 HTTP 代理端口 -> 本地 SOCKS5 端口 -> SSH 隧道 -> 互联网

需要两个端口：
- HTTP_PROXY_PORT: HTTP 代理端口（供 curl/wget/pip/git 等 HTTP 客户端使用）
- SOCKS5_PORT: SOCKS5 代理端口（供 git SSH 等非 HTTP 协议使用）

## 第一步：扫描可用端口

先执行 ss 命令检查当前机器上哪些端口已被占用，特别关注：
- 已经被其他用户占用的端口，绝不可使用
- 只使用当前用户（$USER）未占用的端口

从 17990-17999 范围中选两个未被任何用户占用的端口：
- HTTP_PROXY_PORT = 第一个可用端口
- SOCKS5_PORT = 第二个可用端口

如果该范围全部被占用，从 18990-18999 继续找。

运行以下命令并将结果给我看：
```
ss -H -ltnpe | awk '{print $4}' | grep -oP ':\d+' | sort -t: -k2 -n | uniq
id -u
whoami
```

向我汇报哪些端口可用，我确认后再继续。

## 第二步：配置 ~/.bashrc

在我确认端口后，在 ~/.bashrc 末尾追加以下内容（替换 XXXX 和 YYYY 为实际端口号）：

### 代理变量（默认开启）

```bash
export ALL_PROXY="socks5h://127.0.0.1:XXXX"
export all_proxy="socks5h://127.0.0.1:XXXX"
export HTTP_PROXY="http://127.0.0.1:YYYY"
export HTTPS_PROXY="http://127.0.0.1:YYYY"
export http_proxy="http://127.0.0.1:YYYY"
export https_proxy="http://127.0.0.1:YYYY"
export NO_PROXY="localhost,127.0.0.1,::1,api.deepseek.com,pypi.tuna.tsinghua.edu.cn,mirrors.tuna.tsinghua.edu.cn,pypi.org,files.pythonhosted.org"
export no_proxy="localhost,127.0.0.1,::1,api.deepseek.com,pypi.tuna.tsinghua.edu.cn,mirrors.tuna.tsinghua.edu.cn,pypi.org,files.pythonhosted.org"
```

### Python 包镜像（清华源，不走代理）

```bash
export PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
export UV_DEFAULT_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"
export UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
export UV_HTTP_TIMEOUT="120"
export UV_HTTP_RETRIES="8"
```

### 端口检测函数（仅信任当前用户监听的端口）

```bash
_scc_port_state() {
    local uid
    uid="$(id -u)"
    if command -v ss >/dev/null 2>&1 && ss -H -ltnpe "sport = :$1" 2>/dev/null | grep -Eq "uid:${uid}([[:space:]]|$)"; then
        printf "LISTEN"
    else
        printf "DOWN"
    fi
}

_scc_vpn_ports_ready() {
    [ "$(_scc_port_state YYYY)" = "LISTEN" ] && [ "$(_scc_port_state XXXX)" = "LISTEN" ]
}
```

### vpn 命令（开启/验证代理）

```bash
vpn() {
    if [ $# -eq 0 ]; then
        export ALL_PROXY="socks5h://127.0.0.1:XXXX"
        export all_proxy="socks5h://127.0.0.1:XXXX"
        export HTTP_PROXY="http://127.0.0.1:YYYY"
        export HTTPS_PROXY="http://127.0.0.1:YYYY"
        export http_proxy="http://127.0.0.1:YYYY"
        export https_proxy="http://127.0.0.1:YYYY"
        export NO_PROXY="localhost,127.0.0.1,::1,api.deepseek.com,pypi.tuna.tsinghua.edu.cn,mirrors.tuna.tsinghua.edu.cn,pypi.org,files.pythonhosted.org"
        export no_proxy="localhost,127.0.0.1,::1,api.deepseek.com,pypi.tuna.tsinghua.edu.cn,mirrors.tuna.tsinghua.edu.cn,pypi.org,files.pythonhosted.org"
        _scc_vpn_chain
        return
    fi
    if ! _scc_vpn_ports_ready; then
        echo "VPN链路不可用: YYYY/XXXX 端口必须由当前用户监听"
        _scc_vpn_chain
        return 1
    fi
    HTTP_PROXY="http://127.0.0.1:YYYY" \
    http_proxy="http://127.0.0.1:YYYY" \
    HTTPS_PROXY="http://127.0.0.1:YYYY" \
    https_proxy="http://127.0.0.1:YYYY" \
    ALL_PROXY="socks5h://127.0.0.1:XXXX" \
    all_proxy="socks5h://127.0.0.1:XXXX" \
    NO_PROXY="localhost,127.0.0.1,::1,api.deepseek.com,pypi.tuna.tsinghua.edu.cn,mirrors.tuna.tsinghua.edu.cn,pypi.org,files.pythonhosted.org" \
    no_proxy="localhost,127.0.0.1,::1,api.deepseek.com,pypi.tuna.tsinghua.edu.cn,mirrors.tuna.tsinghua.edu.cn,pypi.org,files.pythonhosted.org" \
    "$@"
}
```

### unvpn 命令（关闭代理）

```bash
unvpn() {
    unset HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY
    unset http_proxy https_proxy all_proxy no_proxy
    echo "VPN代理已关闭: 当前使用本机网络"
}
```

### 链路状态显示函数

```bash
_scc_vpn_chain() {
    local p_http p_socks
    p_http="$(_scc_port_state YYYY)"
    p_socks="$(_scc_port_state XXXX)"
    echo "VPN链路: HTTP 127.0.0.1:YYYY[$p_http] -> SOCKS 127.0.0.1:XXXX[$p_socks]"
    echo "代理变量: HTTP_PROXY=${HTTP_PROXY:-<unset>}  ALL_PROXY=${ALL_PROXY:-<unset>}"
    echo "端口策略: 仅使用当前用户监听的端口，不信任其他用户进程"
}
```

### 启动时自动检查

```bash
_scc_vpn_chain
```

## 第三步：验证

配置完成后运行以下命令验证：

```bash
source ~/.bashrc
vpn         # 应显示链路状态
unvpn       # 应关闭代理
vpn         # 应恢复
ss -H -ltnpe | grep -E "YYYY|XXXX"   # 确认端口归属
```

## 重要约束

1. 绝不修改、停止或占用其他用户（非 $USER）已监听的端口
2. 只追加到 ~/.bashrc，不修改已有内容
3. 不创建 systemd 服务或持久化配置
4. SSH 隧道/VS Code 端口转发由用户自行配置，不在本脚本范围内
5. 端口检测使用 ss 命令按 UID 过滤：`ss -H -ltnpe "sport = :PORT" | grep "uid:$(id -u)"`
```

---

## 你发给对方的完整消息

```
把这个 prompt 发给你的 Codex：

（粘贴上面的 prompt 全部内容）
```

对方只需要在 Codex 中输入这一段即可。Codex 会自动：
1. 扫描 17990-17999 范围内可用端口
2. 汇报可用端口等待确认
3. 追加配置到 ~/.bashrc
4. 验证配置生效
