# FaceSymAi V1 静态图片输入管理规范

V1 输入管理负责在算法评分前校验一组静态图片是否构成可比较样本。它位于质量门控之前/之上：单张图片先通过质量门控，多张图片再做角色、来源和可比性校验。

## 输入要求

- 支持多张静态图片。
- 至少 2 张图片。
- 必须包含一组核心成对输入：
  - `front`：正脸/静息正脸，用于整体对称性、眼部、眉部、鼻面中线和轮廓。
  - `teeth`：露齿/微笑示齿，用于口部对称性、口角下垂和露齿口型。
- 可包含额外静态图，例如侧脸、闭眼、皱眉、舌像等；额外图不替代 `front + teeth` 成对输入。
- 同一输入组应来自同一患者；如果提供 `patient_id`，多个 patient_id 会被拒绝。
- 同一输入组最好来自同一次采集；多个 `capture_id` 会进入 `review`。

## 角色别名

输入管理会把业务字段归一化：

- `front`：`front`、`frontal`、`front_contour`、`正面`、`正脸`、`正脸轮廓`
- `teeth`：`teeth`、`teeth_image`、`smile_teeth`、`smile`、`示齿`、`露齿`、`微笑示齿`

## 可比性检查

核心 `front + teeth` 会比较：

- 图片宽度差异。
- 图片高度差异。
- 亮度均值差异。
- 人脸框短边差异，当前依赖质量门控的人脸检测代理。

差异较大时不会直接删除输入，但会返回 `review`，后续评分应降低可信度或进入人工复核。

## 输出等级

- `pass`：成对输入完整，单图质量可用，整体可比。
- `review`：成对输入完整，但采集来源、尺寸、光照或质量存在可比性风险。
- `reject`：缺少成对输入、只有单张图、混入视频/非图片、跨患者、或单张图片质量被 hard reject。

## CLI

直接传图片：

```bash
scripts/run_in_project_env.sh python scripts/validate_static_inputs.py \
  --image front /path/to/front.jpg \
  --image teeth /path/to/teeth.jpg \
  --pretty
```

使用 JSON：

```json
{
  "images": [
    {
      "path": "/path/to/front.jpg",
      "role": "front",
      "patient_id": "p001",
      "capture_id": "c001"
    },
    {
      "path": "/path/to/teeth.jpg",
      "role": "teeth",
      "patient_id": "p001",
      "capture_id": "c001"
    }
  ]
}
```

```bash
scripts/run_in_project_env.sh python scripts/validate_static_inputs.py \
  --input-json input_set.json \
  --pretty
```

## 代码入口

- `src/facesymai/input_management.py`
- `StaticImageInputManager.validate(...)`
- `scripts/validate_static_inputs.py`
