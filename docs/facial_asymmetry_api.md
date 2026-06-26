# 人脸不对称分析 API 文档

> 服务地址：`http://192.168.17.175:8790`
> 更新时间：2026-06-24
> 规则版本：规则62（稳定性加权特征患病判断规则）

---

## 1. 服务概述

基于规则62（21 个面部对称性特征 + 稳定性加权），对同一受试者的多张图片进行面部不对称性聚合分析。

### 启动服务

```bash
cd /supercloud/llm-code/scc/scc/FaceSymAi
source $(conda info --base)/etc/profile.d/conda.sh && conda activate anti-spoofing_scc_175
PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi \
  python modules/facial_asymmetry_service/serve_web.py --port 8790
```

---

## 2. 接口详情

### 不对称分析

```
POST http://192.168.17.175:8790/api/analyze
Content-Type: multipart/form-data
```

**请求参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| images | file | 是 | 同一受试者图片，可重复上传。最少 2 张，最多 25 张。支持 jpg/jpeg/png，≤25MB |

建议按文件名自动识别动作类型：`front`、`smile`、`teeth`、`front_contour`、`smile_teeth`、`eyes_right`、`eyes_closed`、`forehead_wrinkle`、`frown`。

**文件名不含已知角色时**，服务自动调用动作检测推断角色：

| 检测结果 | 推断角色 |
|---------|---------|
| 侧视（眼球看左/右） | `eyes_right` |
| 露齿 | `smile_teeth` |
| 均未触发 | `front` |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | `ok` |
| analysis.face_asymmetry_output | string | `人脸不对称性较高` / `未达到高置信人脸不对称阈值` / `无法判断` |
| analysis.face_asymmetry_confidence | float | 规则62 加权证据分（0~1） |
| analysis.confidence_level | string | 置信等级 |
| analysis.top_attributions | array | 前 5 项生理归因（区域、观察项、生理含义、贡献权重） |
| analysis.region_results | object | 各面部区域权重占比和触发贡献占比 |
| images[].status_message | string | 每张图片的检测状态 |

**调用示例**

```bash
curl -X POST http://192.168.17.175:8790/api/analyze \
  -F "images=@front.jpg" \
  -F "images=@smile_teeth.jpg"
```

**返回示例**

```json
{
  "status": "ok",
  "analysis": {
    "face_asymmetry_output": "人脸不对称性较高",
    "face_asymmetry_confidence": 0.723,
    "confidence_level": "中",
    "top_attributions": [
      {
        "region": "口部",
        "observation": "口角牵拉幅度左右差",
        "physiological_meaning": "双侧口角运动不对称",
        "weight": 0.85,
        "contribution": 0.152
      }
    ],
    "region_results": {
      "口部": {"weight_ratio": 0.38, "triggered_ratio": 0.45},
      "眼部": {"weight_ratio": 0.25, "triggered_ratio": 0.20}
    }
  },
  "images": [
    {"original_filename": "front.jpg", "status_message": "已识别人脸并纳入分析"},
    {"original_filename": "smile_teeth.jpg", "status_message": "已识别人脸并纳入分析"}
  ]
}
```

---

## 3. 规则62 说明

- 21 个去重推荐面部对称性特征
- 跨数据集 AUC 稳定性 + 非患者 specificity + 图片波动性加权
- 判断阈值：`weighted_disease_score ≥ 0.613`
- `face_asymmetry_confidence` 为加权证据分（0~1），非临床诊断概率
- 基线指标（77 患者测试集）：Precision 0.78 / Recall 0.58 / Specificity 0.72

⚠️ **本服务定位为预警辅助/技术研究，不作为临床诊断工具。**

---

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06-24 | 纯网络 API 服务文档 |
| — | 初版：规则62 服务封装 |
