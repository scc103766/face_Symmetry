#!/usr/bin/env bash
# ============================================================
# pm-workflow export — 导出 PM 工作状态为可迁移归档
# ============================================================
# 用法:
#   ./export.sh [输出文件] [项目目录]
#
# 参数:
#   输出文件    归档文件路径（默认 ./pm-state-YYYY-MM-DD.tar.gz）
#   项目目录    源项目根目录（默认当前目录）
#
# 示例:
#   cd my-project && /path/to/pm-workflow/scripts/export.sh
#   /path/to/pm-workflow/scripts/export.sh ~/backups/project-a.tar.gz /home/me/project-a
# ============================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PROJECT_DIR="${2:-$(pwd)}"
PROJECT_DIR="$(cd "$PROJECT_DIR" 2>/dev/null && pwd)"

# 默认输出文件名
TIMESTAMP=$(date +%Y-%m-%d)
DEFAULT_OUTPUT="./pm-state-${TIMESTAMP}.tar.gz"
OUTPUT_FILE="${1:-$DEFAULT_OUTPUT}"

# 转为绝对路径（如果不是绝对路径）
if [[ "$OUTPUT_FILE" != /* ]]; then
    OUTPUT_FILE="$(pwd)/$OUTPUT_FILE"
fi

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  PM Workflow — 状态导出${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "源项目 : ${PROJECT_DIR}"
echo -e "导出到 : ${OUTPUT_FILE}"
echo ""

# 检查项目目录
if [ ! -f "$PROJECT_DIR/PROJECT_CONTEXT.md" ]; then
    echo -e "${YELLOW}⚠ 未找到 PROJECT_CONTEXT.md，该项目可能未初始化 PM 工作模式${NC}"
    echo "  请先运行 init.sh 初始化项目"
    exit 1
fi

# 创建临时目录
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

echo "正在收集文件..."

# 复制文件到临时目录（保持目录结构）
mkdir -p "$TMPDIR/pm-export"

copy_if_exists() {
    local src="$PROJECT_DIR/$1"
    local dst="$TMPDIR/pm-export/$1"
    if [ -e "$src" ]; then
        # 创建目标父目录
        mkdir -p "$(dirname "$dst")"
        cp -r "$src" "$dst"
        echo -e "  ${GREEN}✓${NC} $1"
    else
        echo -e "  ${YELLOW}⊙${NC} 跳过 $1 (不存在)"
    fi
}

copy_if_exists "PROJECT_CONTEXT.md"
copy_if_exists "WORK_STATUS.md"
copy_if_exists "tasks"
copy_if_exists "sessions"

# 生成导出清单
MANIFEST="$TMPDIR/pm-export/MANIFEST.json"
cat > "$MANIFEST" << MANIFEST_EOF
{
  "export_tool": "pm-workflow",
  "export_version": "1.0",
  "export_date": "$(date -Iseconds)",
  "source_project": "$PROJECT_DIR",
  "hostname": "$(hostname)",
  "contents": {
    "PROJECT_CONTEXT.md": $([ -f "$PROJECT_DIR/PROJECT_CONTEXT.md" ] && echo "true" || echo "false"),
    "WORK_STATUS.md": $([ -f "$PROJECT_DIR/WORK_STATUS.md" ] && echo "true" || echo "false"),
    "tasks": $([ -d "$PROJECT_DIR/tasks" ] && echo "true" || echo "false"),
    "sessions": $([ -d "$PROJECT_DIR/sessions" ] && echo "true" || echo "false")
  }
}
MANIFEST_EOF
echo -e "  ${GREEN}✓${NC} MANIFEST.json"

# 统计
FILE_COUNT=$(find "$TMPDIR/pm-export" -type f | wc -l)
TOTAL_SIZE=$(du -sh "$TMPDIR/pm-export" | cut -f1)

echo ""
echo "收集完成: ${FILE_COUNT} 个文件, ${TOTAL_SIZE}"

# 打包
echo ""
echo "正在打包..."
cd "$TMPDIR"
tar -czf "$OUTPUT_FILE" pm-export/
cd - > /dev/null

ARCHIVE_SIZE=$(du -sh "$OUTPUT_FILE" | cut -f1)

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✓ 导出完成${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "归档文件 : ${OUTPUT_FILE}"
echo "文件数量 : ${FILE_COUNT}"
echo "归档大小 : ${ARCHIVE_SIZE}"
echo ""
echo "迁移到其他机器:"
echo "  scp ${OUTPUT_FILE} user@other-machine:/path/to/"
echo "  然后在目标机器运行: ./scripts/import.sh ${OUTPUT_FILE} /target/project"
echo ""
