#!/usr/bin/env bash
# ==============================================================================
#  data_audit_server122.sh
# ------------------------------------------------------------------------------
#  用途    : 192.168.12.122 内网机数据迁移验收 —— 目录结构与文件数量核验
#  背景    : 原 192.168.12.115 (Windows) 数据集全量迁移至 192.168.12.122 (Ubuntu)
#            本脚本对照 handover/by_person/scc/《内网机数据和算力统计》文档逐数据集核验
#  执行方式: 将本脚本 scp 至 122 后执行，或直接 SSH 后粘贴整段到终端
#            bash data_audit_server122.sh
#  输出    : ① 控制台表格（快速，主要为目录计数，约 3-8 分钟）
#            ② 后台 nohup 任务将各数据集图片/文件总数写入 ${LOG_DIR}/*.count
#  注意    : set -uo pipefail 模式；需 bash ≥ 4.0（ubuntu 默认满足）
#  原始文档: handover/by_person/scc/内网机数据和算力统计：.docx
#  维护    : [验收人填写姓名]
#  日期    : 2026-05-19
# ==============================================================================

set -uo pipefail

# ──────────────────────────────────────────────────────────────────────────────
#  路径常量
# ──────────────────────────────────────────────────────────────────────────────
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly BASE="/media/data/face2/DATA_CENTER_2024"             # 主数据根目录
readonly ZH="/media/face/data/zhenghu/patch_all/zhenghu_path"  # 政务数据
readonly GUOWAI="/media/face/data/public_dataset"              # 国外公开数据集（rec/lst 格式）
readonly PROJECT_TMP_DIR="${FACE_SYM_AI_TMP_DIR:-${SCRIPT_DIR}/tmp}"
readonly LOG_DIR="${PROJECT_TMP_DIR}/data_audit_$(date +%Y%m%d_%H%M%S)"

mkdir -p "${LOG_DIR}"

# ──────────────────────────────────────────────────────────────────────────────
#  辅助函数
# ──────────────────────────────────────────────────────────────────────────────

# 统计指定路径的 1 级子目录数（不排序，速度快）
_count_l1_dirs() {
    find "$1" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l
}

# 统计指定路径的 2 级子目录数（用于"类别数 = partition/person_id"两层结构）
_count_l2_dirs() {
    find "$1" -mindepth 2 -maxdepth 2 -type d 2>/dev/null | wc -l
}

# 打印对齐行：label  实测值  文档期望  统计口径  [✓/△/空]
# exp="—" 表示无文档参考值，不输出对比标记
_row() {
    local label="$1" val="$2" exp="$3" note="$4"
    local mark
    if   [[ "${exp}" == "—" ]];   then mark="  "
    elif [[ "${val}" == "${exp}" ]]; then mark="✓"
    else                                  mark="△"
    fi
    printf "  %-44s  %-12s  %-13s  %s  %s\n" "$label" "$val" "$exp" "$note" "$mark"
}

# 打印节标题
_section() {
    echo ""
    echo "  ┌──────────────────────────────────────────────────────────────────────────┐"
    printf "  │  %-73s│\n" "$1"
    echo "  └──────────────────────────────────────────────────────────────────────────┘"
    printf "  %-44s  %-12s  %-13s  %s\n" "路径 / 说明" "实测值" "文档期望" "统计口径"
    echo "  ──────────────────────────────────────────────────────────────────────────────"
}

# 启动后台文件计数任务（nohup），输出至 LOG_DIR
_bg_count() {
    local label="$1"
    local path="$2"
    local outfile="${LOG_DIR}/$3"
    nohup bash -c "
        echo \"[${label}] 开始: \$(date '+%Y-%m-%d %H:%M:%S')\"
        cnt=\$(find \"${path}\" -type f 2>/dev/null | wc -l)
        echo \"[${label}] 文件总数: \${cnt}\"
        echo \"[${label}] 结束: \$(date '+%Y-%m-%d %H:%M:%S')\"
    " > "${outfile}" 2>&1 &
    printf "  %-14s  PID=%-7d  →  %s\n" "[${label}]" "$!" "${outfile}"
}

# ──────────────────────────────────────────────────────────────────────────────
#  主体输出
# ──────────────────────────────────────────────────────────────────────────────

echo ""
echo "  ╔══════════════════════════════════════════════════════════════════════════╗"
echo "  ║         数据迁移验收报告  ·  192.168.12.122 (Ubuntu)                   ║"
printf "  ║         执行时间 : %-55s║\n" "$(date '+%Y-%m-%d %H:%M:%S')"
printf "  ║         执行用户 : %-55s║\n" "$(whoami)@$(hostname)"
echo "  ╠══════════════════════════════════════════════════════════════════════════╣"
echo "  ║  ✓ = 与文档一致   △ = 差异或待后台统计确认                             ║"
echo "  ╚══════════════════════════════════════════════════════════════════════════╝"


# ════════════════════════════════════════════════════════════════════════════════
#  1/6  haiguan  海关数据
#       原路径 : R:/DataCenter/haiguan
#       新路径 : /media/data/face2/DATA_CENTER_2024/haiguan
#       文档值 : 类别 42,527  图片 2,388,748  均图 56张/类  中年84% 男66% 口罩18%
# ════════════════════════════════════════════════════════════════════════════════
_section "1/6  haiguan  (海关散图数据集)"

path="${BASE}/haiguan"
cats="$(_count_l1_dirs "${path}")"
_row "${path} [类别数]" "${cats}" "42527" "1级子目录(person_id)"

# haiguan_blance：从 haiguan 均衡采样的子集（1:1 性别与年龄分布，文档值 21,243 类）
# ⚠ 该路径在文档末尾 Linux 路径清单中未显式列出，以同级目录推断；若实际位置不同请手动核查
blance_path="${BASE}/haiguan_blance"
if [ -d "${blance_path}" ]; then
    blance_cats="$(_count_l1_dirs "${blance_path}")"
    _row "${blance_path} [类别数·均衡子集]" "${blance_cats}" "21243" "1级子目录(person_id)"
else
    _row "${blance_path} [类别数·均衡子集]" "⚠路径不存在" "21243" "Linux路径清单未列出，需与交接人确认"
fi


# ════════════════════════════════════════════════════════════════════════════════
#  2/6  haiguan_new  海关数据2
#       原路径 : E:/haiguan_new
#       新路径 : /media/data/face2/DATA_CENTER_2024/haiguan_new
#       文档值 : 13个批次  总类别 345,504  总图片 16,865,872  均图 40-42张/类
#       结构   : haiguan_new/{batch}/{person_id}/{img}
# ════════════════════════════════════════════════════════════════════════════════
_section "2/6  haiguan_new  (海关散图数据集2)"

path="${BASE}/haiguan_new"
batches="$(_count_l1_dirs "${path}")"
_row "${path} [批次数]" "${batches}" "13" "1级子目录(batch)"

# 各批次期望类别数（文档原值）
declare -A HN_EXP_CATS=(
    [bg_data_20190419]=30743
    [tmp1]=480      [tmp2]=3366    [tmp3]=2947    [tmp4]=44250
    [tmp5]=2340     [tmp6]=6333    [tmp7]=33232   [tmp8]=35493
    [tmp9]=60830    [tmp10]=54670  [tmp11]=53085  [tmp12]=50967
)
# 各批次期望图片数（文档原值，仅供后台统计参考）
declare -A HN_EXP_IMGS=(
    [bg_data_20190419]=2011014
    [tmp1]=53345    [tmp2]=532911   [tmp3]=347306   [tmp4]=1979945
    [tmp5]=151458   [tmp6]=379229   [tmp7]=1926371  [tmp8]=1639986
    [tmp9]=2582104  [tmp10]=216397  [tmp11]=1554577 [tmp12]=1544329
)

echo ""
printf "  %-44s  %-12s  %-13s  %-16s  %s\n" \
    "  批次子目录" "类别数(实测)" "类别数(期望)" "图片数(期望)" "对比"

for d in bg_data_20190419 tmp1 tmp2 tmp3 tmp4 tmp5 tmp6 tmp7 tmp8 tmp9 tmp10 tmp11 tmp12; do
    p="${path}/${d}"
    if [ ! -d "${p}" ]; then
        printf "  %-44s  %-12s  %-13s  %-16s  %s\n" \
            "  └─ ${d}" "⚠ 目录缺失" "${HN_EXP_CATS[${d}]}" "${HN_EXP_IMGS[${d}]}" "✗"
        continue
    fi
    cats="$(_count_l1_dirs "${p}")"
    [[ "${cats}" == "${HN_EXP_CATS[${d}]}" ]] && mark="✓" || mark="△"
    printf "  %-44s  %-12s  %-13s  %-16s  %s\n" \
        "  └─ ${d}" "${cats}" "${HN_EXP_CATS[${d}]}" "${HN_EXP_IMGS[${d}]}" "${mark}"
done


# ════════════════════════════════════════════════════════════════════════════════
#  3/6  shebao  社保数据
#       原路径 : R:/DataCenter/shebao/
#       新路径 : /media/data/face2/DATA_CENTER_2024/shebao/
#       文档值 : 总类别 2,382,344  总图片 10,531,707  均图 5-6张/类
#       结构   : shebao/{dataset}/{partition}/{person_id}/{img}
# ════════════════════════════════════════════════════════════════════════════════
_section "3/6  shebao  (社保散图数据集 · 含6个子数据集)"

# 期望分区数 | 期望类别数 | 期望图片数
declare -A SB_EXP_PARTS=( [Ahhnpeople]=23   [Ahtlpeople]=22    [cssjpeople]=57
                           [gxpeople]=154    [hbpeople]=11      [lzpeople]=32 )
declare -A SB_EXP_CATS=(  [Ahhnpeople]=179674  [Ahtlpeople]=175283  [cssjpeople]=455113
                           [gxpeople]=1232000   [hbpeople]=84274     [lzpeople]=256000 )
declare -A SB_EXP_IMGS=(  [Ahhnpeople]=492344  [Ahtlpeople]=973050  [cssjpeople]=3190046
                           [gxpeople]=2518255   [hbpeople]=218832    [lzpeople]=3139180 )

for ds in Ahhnpeople Ahtlpeople cssjpeople gxpeople hbpeople lzpeople; do
    p="${BASE}/shebao/${ds}"
    # 兼容大小写（Linux 区分大小写）
    [ ! -d "${p}" ] && p="${BASE}/shebao/${ds,,}"
    if [ ! -d "${p}" ]; then
        _row "  shebao/${ds} [分区数]" "⚠路径缺失" "${SB_EXP_PARTS[${ds}]}" "请核查目录大小写"
        _row "  shebao/${ds} [类别数]" "⚠路径缺失" "${SB_EXP_CATS[${ds}]}"  "请核查目录大小写"
        continue
    fi
    parts="$(_count_l1_dirs "${p}")"
    cats="$(_count_l2_dirs "${p}")"   # 2级目录 = person_id 数；此步约 1-3 分钟
    _row "  shebao/${ds} [分区数]" "${parts}" "${SB_EXP_PARTS[${ds}]}" "1级子目录(partition)"
    _row "  shebao/${ds} [类别数]" "${cats}"  "${SB_EXP_CATS[${ds}]}"  "2级子目录(person_id, 约1-3min)"
    printf "  %-44s  %-12s\n" "  shebao/${ds} [图片数·文档期望参考]" "${SB_EXP_IMGS[${ds}]}"
done


# ════════════════════════════════════════════════════════════════════════════════
#  4/6  hnstpeople  社保-b 数据
#       原路径 : R:/DataCenter/shebao-b/hnstpeople
#       新路径 : /media/data/face2/DATA_CENTER_2024/hnstpeople1535962066849
#       文档值 : 分区 311  类别 2,488,000  图片 14,276,213  均图 5-6张/类
#       结构   : hnstpeople1535962066849/{partition}/{person_id}/{img}
# ════════════════════════════════════════════════════════════════════════════════
_section "4/6  hnstpeople  (社保-b 散图数据集 · 原 shebao-b)"

path="${BASE}/hnstpeople1535962066849"
parts="$(_count_l1_dirs "${path}")"
cats="$(_count_l2_dirs "${path}")"     # 约 3-5 分钟
_row "${path} [分区数]" "${parts}" "311"     "1级子目录(partition)"
_row "${path} [类别数]" "${cats}"  "2488000" "2级子目录(person_id)"


# ════════════════════════════════════════════════════════════════════════════════
#  5/6  zhenghu  政务数据
#       路径   : /media/face/data/zhenghu/patch_all/zhenghu_path
#       文档值 : 总类别 1,409,157  已提取 112,962 类 / 310,725 张  均图 ~3张/类
#       结构   : zhenghu_path/{person_id}/{img}
# ════════════════════════════════════════════════════════════════════════════════
_section "5/6  zhenghu  (政务数据集)"

path="${ZH}"
cats="$(_count_l1_dirs "${path}")"
_row "${path} [类别总数]" "${cats}" "1409157" "1级子目录(person_id)"


# ════════════════════════════════════════════════════════════════════════════════
#  6/6  guowai  国外公开数据集（MXNet RecordIO 格式）
#       原路径 : R:/DataCenter/guowai（Windows）
#       新路径 : /media/face/data/public_dataset
#       文档值 : 类别 672,056  原始图片 4,752,447（已打包为 rec，非散图）
#       文件格式: .rec（图像块）/ .lst（标注列表）/ .idx（索引）
#       注意   : 此数据集为 MXNet RecordIO 预处理产物，不应按散图目录结构验收
# ════════════════════════════════════════════════════════════════════════════════
_section "6/6  guowai  (国外公开数据集 · MXNet RecordIO 格式)"

echo "  ℹ  文件格式说明: .rec = 图像块  .lst = 标注列表  .idx = 索引"
echo "  ℹ  文档期望(参考): 类别约 672,056  原始图片约 4,752,447 (已打包)"
echo ""

path="${GUOWAI}"
if [ ! -d "${path}" ]; then
    echo "  ⚠  路径不存在: ${path}"
    echo "  ⚠  请确认 /media/face 挂载状态:  df -h | grep face"
else
    rec_cnt=$(find "${path}" -name "*.rec" 2>/dev/null | wc -l)
    lst_cnt=$(find "${path}" -name "*.lst" 2>/dev/null | wc -l)
    idx_cnt=$(find "${path}" -name "*.idx" 2>/dev/null | wc -l)
    total_f=$(find "${path}" -type f      2>/dev/null | wc -l)
    total_sz=$(du -sh "${path}" 2>/dev/null | awk '{print $1}')

    _row "${path} [.rec 文件数]"   "${rec_cnt}" "—" "find -name '*.rec'"
    _row "${path} [.lst 文件数]"   "${lst_cnt}" "—" "find -name '*.lst'"
    _row "${path} [.idx 文件数]"   "${idx_cnt}" "—" "find -name '*.idx'"
    _row "${path} [全部文件总数]"  "${total_f}"  "—" "find -type f"
    echo ""
    printf "  %-44s  %s\n" "  总占用磁盘空间" "${total_sz}"
    echo ""
    echo "  目录结构预览:"
    ls -lhp "${path}" 2>/dev/null | head -40 | sed 's/^/    /'
fi


# ════════════════════════════════════════════════════════════════════════════════
#  后台图片/文件总数统计（慢速，nohup 后台执行）
# ════════════════════════════════════════════════════════════════════════════════
echo ""
echo "  ══════════════════════════════════════════════════════════════════════════"
echo "  后台统计任务 (图片/文件总数 · 约 10-60 分钟/数据集)"
echo "  日志目录: ${LOG_DIR}"
echo "  ══════════════════════════════════════════════════════════════════════════"

_bg_count "haiguan"      "${BASE}/haiguan"                   "haiguan.count"
_bg_count "haiguan_new"  "${BASE}/haiguan_new"               "haiguan_new.count"
_bg_count "shebao"       "${BASE}/shebao"                    "shebao.count"
_bg_count "hnstpeople"   "${BASE}/hnstpeople1535962066849"   "hnstpeople.count"
_bg_count "zhenghu"      "${ZH}"                             "zhenghu.count"

echo ""
echo "  文档期望图片数 (后台结果对照):"
printf "  %-16s %-16s %-16s %-16s %-14s\n" \
    "haiguan" "haiguan_new" "shebao" "hnstpeople" "zhenghu"
printf "  %-16s %-16s %-16s %-16s %-14s\n" \
    "2,388,748" "16,865,872" "10,531,707" "14,276,213" "~4,227,471"
echo ""
echo "  查看进度: watch -n 30 'ls -lh ${LOG_DIR}/'"
echo "  查看结果: cat ${LOG_DIR}/*.count"
echo ""


# ════════════════════════════════════════════════════════════════════════════════
#  汇总
# ════════════════════════════════════════════════════════════════════════════════
echo "  ══════════════════════════════════════════════════════════════════════════"
echo "  验收完成（快速部分）"
echo "  ✓ = 与文档一致   △ = 存在差异或待后台统计确认   ✗ = 路径缺失"
echo "  ══════════════════════════════════════════════════════════════════════════"
echo ""
