#!/usr/bin/env bash
# ============================================================
# pm-workflow init — 在新项目中初始化 PM 工作模式骨架
# ============================================================
# 用法:
#   ./init.sh [项目目录] [--force]
#
# 参数:
#   项目目录    目标项目根目录（默认当前目录）
#   --force     强制覆盖已有文件
#
# 示例:
#   cd my-project && /path/to/pm-workflow/scripts/init.sh
#   /path/to/pm-workflow/scripts/init.sh /home/me/new-project
# ============================================================

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_DIR="${1:-$(pwd)}"
FORCE=false

# 解析 --force
shift 2>/dev/null || true
for arg in "$@"; do
    case "$arg" in
        --force|-f) FORCE=true ;;
    esac
done

# 转为绝对路径
PROJECT_DIR="$(cd "$PROJECT_DIR" 2>/dev/null && pwd || echo "$PROJECT_DIR")"

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  PM Workflow — 项目初始化${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "Skill 目录 : ${SKILL_DIR}"
echo -e "项目目录   : ${PROJECT_DIR}"
echo ""

# 检查 skill 完整性
check_asset() {
    local file="$1"
    if [ ! -f "$SKILL_DIR/$file" ]; then
        echo -e "${RED}✗ 缺少模板文件: $file${NC}"
        echo "  请确保 pm-workflow skill 完整安装"
        exit 1
    fi
}

check_asset "assets/PROJECT_CONTEXT.md"
check_asset "assets/WORK_STATUS.md"
check_asset "assets/tasks_README.md"
check_asset "assets/sessions_README.md"

# 创建项目目录（如果不存在）
if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${YELLOW}项目目录不存在，正在创建...${NC}"
    mkdir -p "$PROJECT_DIR"
fi

# 检查是否已有 PM 骨架
has_existing=false
if [ -f "$PROJECT_DIR/PROJECT_CONTEXT.md" ] || [ -d "$PROJECT_DIR/tasks" ] || [ -d "$PROJECT_DIR/sessions" ]; then
    has_existing=true
fi

if $has_existing && ! $FORCE; then
    echo -e "${YELLOW}⚠ 项目目录中已存在 PM 骨架文件${NC}"
    echo ""
    echo "已检测到:"
    [ -f "$PROJECT_DIR/PROJECT_CONTEXT.md" ] && echo "  • PROJECT_CONTEXT.md"
    [ -d "$PROJECT_DIR/tasks" ]           && echo "  • tasks/"
    [ -d "$PROJECT_DIR/sessions" ]        && echo "  • sessions/"
    [ -f "$PROJECT_DIR/WORK_STATUS.md" ]  && echo "  • WORK_STATUS.md"
    echo ""
    echo -e "使用 ${GREEN}--force${NC} 强制覆盖已有文件"
    echo "或手动删除后重新初始化"
    exit 1
fi

# ── 创建骨架 ──────────────────────────────────────────────

echo "正在创建项目骨架..."

create_file() {
    local src="$SKILL_DIR/$1"
    local dst="$PROJECT_DIR/$2"
    local label="$3"

    if [ -f "$dst" ] && ! $FORCE; then
        echo -e "  ${YELLOW}⊙${NC} 跳过 $label (已存在)"
    else
        cp "$src" "$dst"
        echo -e "  ${GREEN}✓${NC} 创建 $label"
    fi
}

create_dir() {
    local dir="$PROJECT_DIR/$1"
    local label="$2"
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo -e "  ${GREEN}✓${NC} 创建目录 $label"
    else
        echo -e "  ${YELLOW}⊙${NC} 目录已存在 $label"
    fi
}

# 核心文件
create_file "assets/PROJECT_CONTEXT.md"  "PROJECT_CONTEXT.md"  "PROJECT_CONTEXT.md"
create_file "assets/WORK_STATUS.md"      "WORK_STATUS.md"      "WORK_STATUS.md"

# tasks/
create_dir "tasks/queue"     "tasks/queue/"
create_dir "tasks/done"      "tasks/done/"
create_dir "tasks/rejected"  "tasks/rejected/"
create_file "assets/tasks_README.md" "tasks/README.md" "tasks/README.md"

# sessions/
create_dir "sessions/project" "sessions/project/"
create_dir "sessions/meta"    "sessions/meta/"
create_file "assets/sessions_README.md" "sessions/README.md" "sessions/README.md"

# .gitkeep 保持空目录
for d in tasks/queue tasks/done tasks/rejected sessions/project sessions/meta; do
    touch "$PROJECT_DIR/$d/.gitkeep"
done

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✓ PM 工作模式骨架已创建${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "创建的文件:"
echo "  📄 PROJECT_CONTEXT.md    — 项目上下文（请填充项目信息）"
echo "  📄 WORK_STATUS.md        — 工作状态追踪（断点恢复）"
echo "  📂 tasks/queue/          — 待执行任务队列"
echo "  📂 tasks/done/           — 已完成任务回报"
echo "  📂 tasks/rejected/       — 已退回任务"
echo "  📂 sessions/project/     — 项目推进会话归档"
echo "  📂 sessions/meta/        — 元问题会话归档"
echo ""
echo "下一步:"
echo "  1. 编辑 PROJECT_CONTEXT.md 填入项目基本信息"
echo "  2. 对 PM Agent 说「启用 PM 工作模式」启动工作流"
echo ""
