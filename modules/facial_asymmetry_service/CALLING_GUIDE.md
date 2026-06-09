# FaceSymAi 人脸不对称服务调用文档

本文档说明如何从外部网络、网页和代码调用 `modules/facial_asymmetry_service`。

## 启动服务

默认会绑定 `0.0.0.0`，允许局域网/外部网络访问。外网暴露时建议设置 `--access-token`。

```bash
scripts/run_in_project_env.sh python modules/facial_asymmetry_service/serve_web.py \
  --port 8790 \
  --access-token <token>
```

如果服务位于反向代理或公网域名后面，可以传入对外地址，启动日志会打印该地址：

```bash
scripts/run_in_project_env.sh python modules/facial_asymmetry_service/serve_web.py \
  --port 8790 \
  --access-token <token> \
  --public-url https://your-domain.example/facesym
```

外部机器需要满足网络条件：

- 服务进程绑定 `0.0.0.0`。
- 服务器防火墙/安全组放行端口，例如 `8790`。
- 如果有反向代理，需要把 `/`、`/api/input-spec`、`/api/analyze` 转发到该服务。

## 网页调用

浏览器访问：

```text
http://<服务器IP>:8790/?token=<token>
```

网页会直接返回分析结果，包括：

- 人脸不对称性判断。
- `face_asymmetry_confidence` 置信度。
- 置信等级。
- 用户可读原因。
- 主要观察项，例如双侧口角夹角、唇部中线偏移、双侧眼裂高度差、眉部高度差、面部轮廓左右差。

## 输入要求

- 支持 `.jpg`、`.jpeg`、`.png`。
- 同一人最少 `2` 张，最多 `10` 张。
- 动作不强制限制。
- 每张图片需要能被 MediaPipe Face Landmarker 检出人脸，并输出 `478 raw landmarks`、`52 blendshapes` 和 transformation matrix。

推荐动作按用户可理解的面部不对称观察价值排序：

1. `smile_teeth` / `smile` / `teeth`：优先推荐，用于观察双侧口角夹角、口角牵拉幅度和唇部中线偏移。
2. `front_contour` / `front`：推荐，用于观察静息状态下面部轮廓、双侧眼裂高度和眉部高度差。
3. `eyes_right`、`eyes_closed`、`forehead_wrinkle`、`frown` 或其他清晰单人脸图片：用于补充观察眼周和额眉部动作差异。

## API

### 输入规范

```http
GET /api/input-spec?token=<token>
```

示例：

```bash
curl "http://<服务器IP>:8790/api/input-spec?token=<token>"
```

### 图片分析

```http
POST /api/analyze?token=<token>
Content-Type: multipart/form-data
```

字段名会用于推断 role。推荐字段名：

- `smile_teeth`
- `front_contour`
- `eyes_right`
- `extra_images`

也可以使用任意字段名，服务会从文件名识别 `front_contour`、`smile_teeth`、`front`、`smile`、`teeth`、`eyes_right`、`eyes_closed`、`forehead_wrinkle`、`frown`。无法识别时按 `unknown` 处理，仍可参与 `all` scope。

## curl 示例

```bash
curl -X POST "http://<服务器IP>:8790/api/analyze?token=<token>" \
  -F "smile_teeth=@smile_teeth.jpg" \
  -F "front_contour=@front.jpg" \
  -F "extra_images=@other.jpg"
```

也可以把 token 放在请求头：

```bash
curl -X POST "http://<服务器IP>:8790/api/analyze" \
  -H "X-Access-Token: <token>" \
  -F "smile_teeth=@smile_teeth.jpg" \
  -F "front_contour=@front.jpg"
```

## Python 调用示例

```python
from pathlib import Path

import requests


base_url = "http://<服务器IP>:8790"
token = "<token>"

image_paths = {
    "smile_teeth": Path("smile_teeth.jpg"),
    "front_contour": Path("front.jpg"),
    "extra_images": Path("other.jpg"),
}

files = []
handles = []
try:
    for field_name, path in image_paths.items():
        handle = path.open("rb")
        handles.append(handle)
        files.append((field_name, (path.name, handle, "image/jpeg")))

    response = requests.post(
        f"{base_url}/api/analyze",
        headers={"X-Access-Token": token},
        files=files,
        timeout=120,
    )
    response.raise_for_status()
    result = response.json()
finally:
    for handle in handles:
        handle.close()

analysis = result["analysis"]
print("判断:", analysis["face_asymmetry_output"])
print("置信度:", analysis["face_asymmetry_confidence"])
print("原因:", analysis["reason_description"])
```

## JavaScript 调用示例

```javascript
const form = new FormData();
form.append("smile_teeth", smileTeethFile);
form.append("front_contour", frontFile);

const response = await fetch("http://<服务器IP>:8790/api/analyze", {
  method: "POST",
  headers: { "X-Access-Token": "<token>" },
  body: form,
});

if (!response.ok) {
  throw new Error(await response.text());
}

const result = await response.json();
console.log(result.analysis.face_asymmetry_output);
console.log(result.analysis.face_asymmetry_confidence);
console.log(result.analysis.reason_description);
```

## 主要返回字段

```json
{
  "analysis": {
    "face_asymmetry_output": "人脸不对称性较高",
    "face_asymmetry_confidence": 0.618647,
    "confidence_percent": 61.86,
    "confidence_level": "较高",
    "predicted_high_asymmetry": true,
    "reason_description": "...",
    "findings": [
      {
        "name": "双侧口角夹角或牵拉幅度差",
        "description": "...",
        "evidence_level": "主要表现",
        "observed_in": ["露齿微笑"]
      }
    ],
    "suggestion": "..."
  },
  "images": [],
  "input_requirements": {},
  "upload": {
    "request_dir": "...",
    "analysis_path": "..."
  }
}
```

字段说明：

- `analysis.face_asymmetry_output`：最终输出。
- `analysis.face_asymmetry_confidence`：62 规则加权证据分，范围 0-1，不是临床诊断概率。
- `analysis.confidence_level`：较低、中等或较高。
- `analysis.reason_description`：中文解释。
- `analysis.findings`：用户可读的主要观察项。
- `images[].status`：每张图片的 MediaPipe 检测状态。
- `images[].status_message`：每张图片是否纳入分析。

## 错误返回

常见错误：

- `400`：图片数量小于 2、超过 10、文件格式不支持、图片为空。
- `401`：token 不正确或缺失。
- `500`：服务端检测或推理异常。

示例：

```json
{
  "error": "同一人最多上传 10 张图片。",
  "input_requirements": {}
}
```

## 安全与边界

- 外网访问时必须保护 token，并建议通过 HTTPS 反向代理暴露。
- 上传图片和分析 JSON 会保存到 `tmp/facial_asymmetry_service_uploads/<request_id>/`。
- 输出是面部对称性辅助分析，不是临床诊断结论。
