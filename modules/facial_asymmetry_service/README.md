# FaceSymAi 人脸不对称分析服务

该模块把当前推荐的 `62_stable_weighted_feature_disease_rule` 封装成可复用服务层。服务输入同一名受试者/同一次采集的一张或多张图片，先调用 `modules/mediapipe_face_keypoint_detector` 生成 MediaPipe 关键点、blendshape 和 transformation matrix，再按 62 规则输出人脸不对称性置信度和原因归因。

## 规则来源

- 特征权重：`datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_feature_weights.csv`
- 总分阈值：`datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_score_threshold.csv`
- 当前判断阈值：`weighted_disease_score >= 0.612826` 输出 `人脸不对称性较高`

`face_asymmetry_confidence` 使用 62 规则的加权证据分，范围为 0-1。它不是临床诊断概率。

## 输入格式

服务接受 `.jpg`、`.jpeg`、`.png`。一次调用中的所有图片会作为同一名受试者的一组证据进行聚合。

规范输入需要满足 MediaPipe Face Landmarker 可用输出要求：

- 能检出人脸。
- 输出 `478` 个 raw landmarks。
- 输出 face blendshapes。
- 输出 facial transformation matrixes。

服务不强制限制动作，但同一受试者最少 `2` 张、最多 `25` 张。按面部不对称的观察价值，推荐优先提供：

- `smile_teeth`，或旧数据中的 `smile` / `teeth`：露齿微笑/口部动态图片，用于观察双侧口角夹角、口角牵拉幅度和唇部中线是否左右不一致。
- `front` 或 `front_contour`：正脸/面部轮廓静态图，用于观察静息状态下面部轮廓、唇中线、眼裂和眉部高度差。
- `eyes_right`、`eyes_closed`、`forehead_wrinkle`、`frown` 或其他清晰单人脸图片：用于补充观察眼周、额眉部和整体面部轮廓的左右差异。

服务可从文件名识别这些 role：`front_contour`、`smile_teeth`、`front`、`smile`、`teeth`、`eyes_right`、`eyes_closed`、`forehead_wrinkle`、`frown`。文件名无法识别时，用 `--role` 或 `--image-role PATH=role` 指定。只提供未知 role 时，服务仍可分析，但口角牵拉、示齿和微笑相关观察会偏少，置信度会偏保守。

## 命令行使用

```bash
scripts/run_in_project_env.sh python modules/facial_asymmetry_service/run_analyze.py \
  path/to/front_contour.jpg \
  path/to/smile_teeth.jpg \
  --output tmp/facial_asymmetry_service_result.json \
  --pretty
```

生成关键点覆盖图：

```bash
scripts/run_in_project_env.sh python modules/facial_asymmetry_service/run_analyze.py \
  path/to/images \
  --recursive \
  --annotated-output tmp/facial_asymmetry_service_annotated \
  --output tmp/facial_asymmetry_service_result.json \
  --pretty
```

手动指定 role：

```bash
scripts/run_in_project_env.sh python modules/facial_asymmetry_service/run_analyze.py \
  a.jpg b.jpg \
  --image-role a.jpg=front_contour \
  --image-role b.jpg=smile_teeth \
  --output tmp/facial_asymmetry_service_result.json \
  --pretty
```

## 网页上传服务

网页服务默认绑定 `0.0.0.0`，可被局域网/外部网络访问。当前部署不启用访问 token：

```bash
scripts/run_in_project_env.sh python modules/facial_asymmetry_service/serve_web.py \
  --port 8790
```

如果现场需要鉴权，可以在启动时增加 `--access-token <your-token>`；只有显式设置该参数后，网页和 API 才需要 token。

网页地址形如：

```text
http://192.168.17.175:8790/
```

完整网页/API/Python/JavaScript 调用说明见 `modules/facial_asymmetry_service/CALLING_GUIDE.md`。
如果调用方需要显式执行“先关键点检测、再人脸不对称推理”的两步链路，见
`modules/facial_asymmetry_service/TWO_STEP_API_CALLING_GUIDE.md`。

上传页面会提示同一人最少 `2` 张、最多 `25` 张，动作不强制限制。推荐动作按用户可理解的观察价值排序：

- 优先 `smile_teeth/smile/teeth`：观察双侧口角夹角、口角牵拉幅度、唇部中线偏移。
- 推荐 `front_contour/front`：观察静息状态下面部轮廓、双侧眼裂高度、眉部高度差。
- 可补充 `eyes_right/eyes_closed/forehead_wrinkle/frown` 或其他清晰单人脸图片：观察眼周和额眉部动作差异。

外部系统可直接调用：

```bash
curl -X POST "http://192.168.17.175:8790/api/analyze" \
  -F "smile_teeth=@smile_teeth.jpg" \
  -F "front_contour=@front.jpg" \
  -F "eyes_right=@other_action.jpg"
```

输入规范接口：

```bash
curl "http://192.168.17.175:8790/api/input-spec"
```

上传分析结果会保存到项目内：

```text
tmp/facial_asymmetry_service_uploads/<request_id>/analysis.json
```

## 输出字段

- `analysis.face_asymmetry_output`：`人脸不对称性较高`、`未达到高置信人脸不对称阈值` 或 `无法判断`。
- `analysis.face_asymmetry_confidence`：62 规则加权证据分。
- `analysis.confidence_level`：置信等级。
- `analysis.top_attributions`：前 5 项生理归因，按医学优先级加权贡献排序，包含区域、观察项、生理含义、阈值、权重、医学优先分和相关图片。
- `analysis.region_results`：面部区域权重占比和触发贡献占比。
- `analysis.feature_region_results`：21 项特征的区域分类与排序结果，包含 `medical_priority_score`、`medical_priority_multiplier` 和 `medical_priority_contribution`。
- `images[].status_message`：每张图片是否已识别人脸并纳入分析。

## 边界

该服务的默认假设是“患病样本具有更高人脸不对称性”，并使用患者弱标签训练出的 62 规则作为当前工程判断规则。输出可用于人脸不对称性证据归因和产品提示，不应用作临床诊断结论。
