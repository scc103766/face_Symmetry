#!/usr/bin/env bash
# ============================================================
# pm-workflow import — 从归档恢复 PM 工作状态
# ============================================================
# 用法:
#   ./import.sh <归档文件> [项目目录] [--force]
#
# 参数:
#   归档文件   由 export.sh 生成的 .tar.gz 文件
#   项目目录   目标项目根目录（默认当前目录）
#   --force    强制覆盖已有文件
#
# 示例:
#   /path/to/pm-workflow/scripts/import.sh ./pm-state-2026-06-10.tar.gz
#   /path/to/pm-workflow/scripts/import.sh backup.tar.gz /home/me/new-project --force
# ============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 参数解析
ARCHIVE_FILE=""
PROJECT_DIR=""
FORCE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --force|-f) FORCE=true; shift ;;
        *)
            if [ -z "$ARCHIVE_FILE" ]; then
                ARCHIVE_FILE="$1"
            elif [ -z "$PROJECT_DIR" ]; then
                PROJECT_DIR="$1"
            fi
            shift
            ;;
    esac
done

PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
PROJECT_DIR="$(cd "$PROJECT_DIR" 2>/dev/null && pwd || echo "$PROJECT_DIR")"

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  PM Workflow — 状态导入${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "归档文件 : ${ARCHIVE_FILE}"
echo -e "目标项目 : ${PROJECT_DIR}"
echo ""

# 验证归档文件
if [ ! -f "$ARCHIVE_FILE" ]; then
    echo -e "${RED}✗ 归档文件不存在: ${ARCHIVE_FILE}${NC}"
    exit 1
fi

# 验证格式
# 注: tar | head 会导致 SIGPIPE (141)，管道中用 { ...; } 包裹避免 set -e 退出
FIRST_LINE=$( { tar -tzf "$ARCHIVE_FILE" 2>/dev/null || true; } | head -n 1 )
if [[ "$FIRST_LINE" != pm-export/* ]] && [[ "$FIRST_LINE" != "pm-export/" ]]; then
    echo -e "${RED}✗ 无效的归档格式（缺少 pm-export/ 根目录）${NC}"
    echo "  实际首行: ${FIRST_LINE}"
    echo "  请确认文件由 pm-workflow export.sh 生成"
    exit 1
fi

# 检查目标项目
if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${YELLOW}目标项目目录不存在，正在创建...${NC}"
    mkdir -p "$PROJECT_DIR"
fi

# 冲突检测
has_conflict=false
if [ -f "$PROJECT_DIR/PROJECT_CONTEXT.md" ] || [ -f "$PROJECT_DIR/WORK_STATUS.md" ]; then
    has_conflict=true
fi

if $has_conflict && ! $FORCE; then
    echo -e "${YELLOW}⚠ 目标项目已存在 PM 文件，可能造成覆盖${NC}"
    echo ""
    echo "已存在的文件:"
    [ -f "$PROJECT_DIR/PROJECT_CONTEXT.md" ] && echo "  • PROJECT_CONTEXT.md"
    [ -f "$PROJECT_DIR/WORK_STATUS.md" ] && echo "  • WORK_STATUS.md"
    [ -d "$PROJECT_DIR/tasks" ]           && echo "  • tasks/"
    [ -d "$PROJECT_DIR/sessions" ]        && echo "  • sessions/"
    echo ""
    echo -e "使用 ${GREEN}--force${NC} 强制导入（会覆盖已有文件）"
    echo "或先导出当前状态、备份后再导入"
    exit 1
fi

# 解压到临时目录先验证
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

echo "正在解压归档..."
tar -xzf "$ARCHIVE_FILE" -C "$TMPDIR"

# 读取清单
MANIFEST="$TMPDIR/pm-export/MANIFEST.json"
if [ -f "$MANIFEST" ]; then
    echo ""
    echo "归档信息:"
    EXPORT_DATE=$(grep -o '"export_date": "[^"]*"' "$MANIFEST" 2>/dev/null | cut -d'"' -f4 || echo "未知")
    SOURCE_PROJ=$(grep -o '"source_project": "[^"]*"' "$MANIFEST" 2>/dev/null | cut -d'"' -f4 || echo "未知")
    SOURCE_HOST=$(grep -o '"hostname": "[^"]*"' "$MANIFEST" 2>/dev/null | cut -d'"' -f4 || echo "未知")
    echo "  导出时间 : ${EXPORT_DATE}"
    echo "  来源项目 : ${SOURCE_PROJ}"
    echo "  来源主机 : ${SOURCE_HOST}"
fi

# 复制文件到目标项目
echo ""
echo "正在导入文件..."

import_item() {
    local src="$TMPDIR/pm-export/$1"
    local dst="$PROJECT_DIR/$1"

    if [ ! -e "$src" ]; then
        return
    fi

    # 创建目标父目录
    mkdir -p "$(dirname "$dst")"

    # 如果是目录，递归复制
    if [ -d "$src" ]; then
        # 清空目标目录（如果强制）
        if $FORCE && [ -d "$dst" ]; then
            rm -rf "$dst"
        fi
        cp -r "$src" "$dst"
        local count=$(find "$dst" -type f | wc -l)
        echo -e "  ${GREEN}✓${NC} $1 (${count} 个文件)"
    else
        cp "$src" "$dst"
        echo -e "  ${GREEN}✓${NC} $1"
    fi
}

import_item "PROJECT_CONTEXT.md"
import_item "WORK_STATUS.md"
import_item "tasks"
import_item "sessions"
import_item "MANIFEST.json"

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✓ 导入完成${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "已恢复到: ${PROJECT_DIR}"
echo ""
echo "下一步:"
echo "  对 PM Agent 说「启用 PM 工作模式」→ PM 自动检测 WORK_STATUS.md 并汇报中断点"
echo ""
