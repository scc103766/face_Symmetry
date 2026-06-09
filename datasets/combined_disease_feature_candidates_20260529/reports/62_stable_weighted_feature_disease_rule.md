# 62 稳定性加权特征患病判断规则

## 方法

- 特征来源：60 阶段去重后的 21 个推荐特征。
- 单特征阈值：每个特征在两批数据的患者级聚合值上搜索阈值。
- 不患病表现：每个特征都计算旧/新/合并 specificity 和不患病误判率，非患者中越少超过阈值权重越高。
- 图片波动性：在对应 role scope 的所有图片上计算 IQR、robust CV、IQR/患者中位数差距；波动越大权重越低。
- 图片总数：图片数越多，证据稳定性越高，权重有小幅增加。
- 权重公式：`0.30*跨数据AUC稳定分 + 0.20*合并AUC分 + 0.25*非患者specificity分 + 0.15*图片波动稳定分 + 0.10*图片数分`，之后归一化为总和 1。
- 特征触发：仅使用理论和数据上均表现为患者更高的特征；患者级特征值 `>=` 单特征阈值时贡献该特征权重。
- 患者判断：所有特征按权重累计，触发特征的权重相加得到 `weighted_disease_score`。
- 加权总分阈值选择：在旧+新全部患者级加权得分上搜索阈值，按 Youden J、balanced accuracy、F1、precision、specificity、score_threshold 依次择优。
- 当前加权总分阈值：`weighted_disease_score >= 0.612826` 输出 `患病倾向较高`。

## 特征权重

| rank | feature | role | agg | threshold | weight | grade | nonpatient_fp_rate | volatility_score | image_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | bsdiff_mouth_abs | mouth_dynamic | max | 0.003855 | 0.057616 | high | 0.269912 | 0.273402 | 1132 |
| 2 | bsdiff_mouth_lateral_abs | mouth_dynamic | max | 0.003855 | 0.057616 | high | 0.269912 | 0.273402 | 1132 |
| 3 | bsdiff_browDown_abs | all | max | 0.013388 | 0.054691 | medium | 0.475771 | 0.534065 | 5330 |
| 4 | raw_lip_midline_deviation | mouth_dynamic | max | 0.008995 | 0.054497 | medium | 0.314159 | 0.301043 | 1132 |
| 5 | raw_iris_region_point_spread_asym | mouth_dynamic | max | 0.009759 | 0.051983 | medium | 0.464602 | 0.336346 | 1132 |
| 6 | bsdiff_mouthFrown_abs | mouth_dynamic | median | 0.000216 | 0.051817 | medium | 0.548673 | 0.175977 | 1132 |
| 7 | raw_face_oval_region_height_asym | all | max | 0.017991 | 0.051482 | medium | 0.211454 | 0.302397 | 5330 |
| 8 | raw_all_mesh_region_height_asym | all | max | 0.017991 | 0.051269 | medium | 0.215859 | 0.306208 | 5330 |
| 9 | raw_iris_region_area_asym | mouth_dynamic | max | 0.019940 | 0.047742 | medium | 0.438053 | 0.277184 | 1132 |
| 10 | raw_eyebrow_region_height_asym | all | median | 0.036786 | 0.047351 | medium | 0.634361 | 0.234978 | 5330 |
| 11 | bsdiff_all_mean_abs | mouth_dynamic | max | 0.047040 | 0.047221 | medium | 0.314159 | 0.330048 | 1132 |
| 12 | raw_eye_region_point_spread_asym | mouth_dynamic | median | 0.010618 | 0.046633 | medium | 0.442478 | 0.269396 | 1132 |
| 13 | raw_mouth_corner_vertical_asym | all | median | 0.017494 | 0.046206 | medium | 0.475771 | 0.272693 | 5330 |
| 14 | raw_face_oval_region_centroid_y_asym | all | median | 0.026082 | 0.045566 | medium | 0.519824 | 0.255947 | 5330 |
| 15 | raw_eyebrow_region_centroid_y_asym | all | max | 0.060332 | 0.044608 | low | 0.418502 | 0.294490 | 5330 |
| 16 | raw_eyebrow_region_point_spread_asym | mouth_dynamic | max | 0.012080 | 0.042995 | low | 0.588496 | 0.281020 | 1132 |
| 17 | raw_eyebrow_region_area_asym | all | median | 0.045246 | 0.042481 | low | 0.691630 | 0.224941 | 5330 |
| 18 | raw_iris_region_centroid_y_asym | all | mean | 0.017457 | 0.040611 | low | 0.616740 | 0.215551 | 5330 |
| 19 | raw_brow_outer_height_asym | all | mean | 0.027565 | 0.039758 | low | 0.647577 | 0.233465 | 5330 |
| 20 | raw_eye_region_centroid_y_asym | all | mean | 0.017110 | 0.039485 | low | 0.625551 | 0.203379 | 5330 |
| 21 | bsdiff_eyeLookDown_abs | mouth_dynamic | max | 0.014890 | 0.038373 | low | 0.570796 | 0.246430 | 1132 |

## 患者级表现

| dataset | patients | TP | FP | TN | FN | precision | recall | specificity | bacc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combined | 605 | 220 | 63 | 164 | 158 | 0.777385 | 0.582011 | 0.722467 | 0.652239 |
| old | 504 | 211 | 59 | 109 | 125 | 0.781481 | 0.627976 | 0.648810 | 0.638393 |
| new | 101 | 9 | 4 | 55 | 33 | 0.692308 | 0.214286 | 0.932203 | 0.573245 |

## 判断原因示例

| patient | dataset | truth | score | triggered | reason |
| --- | --- | --- | --- | --- | --- |
| pid607664443302 | new | 患病 | 0.618647 | 13 | 加权得分 0.618647 >= 阈值 0.612826；触发 13/21 个特征，触发权重 0.618647。主要原因：#1 raw_lip_midline_deviation=0.010222>=阈值0.008995 权重0.054497;#2 raw_eyebrow_region_height_asym=0.071182>=阈值0.036786 权重0.047351;#3 raw_iris_region_point_spread_asym=0.026426>=阈值0.009759 权重0.051983;#5 bsdiff_mouth_abs=0.003858>=阈值0.003855 权重0.057616;#6 bsdiff_mouth_lateral_abs=0.003858>=阈值0.003855 权重0.057616;#8 raw_iris_region_area_asym=0.046704>=阈值0.019940 权重0.047742;#10 raw_eyebrow_region_point_spread_asym=0.015791>=阈值0.012080 权重0.042995;#12 raw_face_oval_region_centroid_y_asym=0.053400>=阈值0.026082 权重0.045566;#13 bsdiff_all_mean_abs=0.060576>=阈值0.047040 权重0.047221;#14 raw_mouth_corner_vertical_asym=0.023828>=阈值0.017494 权重0.046206;#15 raw_iris_region_centroid_y_asym=0.044969>=阈值0.017457 权重0.040611;#16 raw_brow_outer_height_asym=0.065933>=阈值0.027565 权重0.039758;#18 raw_eye_region_centroid_y_asym=0.043910>=阈值0.017110 权重0.039485 |
| pid607669859645 | new | 患病 | 0.680106 | 15 | 加权得分 0.680106 >= 阈值 0.612826；触发 15/21 个特征，触发权重 0.680106。主要原因：#1 raw_lip_midline_deviation=0.009709>=阈值0.008995 权重0.054497;#2 raw_eyebrow_region_height_asym=0.127642>=阈值0.036786 权重0.047351;#3 raw_iris_region_point_spread_asym=0.020164>=阈值0.009759 权重0.051983;#7 bsdiff_mouthFrown_abs=0.000643>=阈值0.000216 权重0.051817;#8 raw_iris_region_area_asym=0.034340>=阈值0.019940 权重0.047742;#9 raw_eye_region_point_spread_asym=0.017928>=阈值0.010618 权重0.046633;#10 raw_eyebrow_region_point_spread_asym=0.015508>=阈值0.012080 权重0.042995;#11 raw_eyebrow_region_area_asym=0.156086>=阈值0.045246 权重0.042481;#12 raw_face_oval_region_centroid_y_asym=0.043318>=阈值0.026082 权重0.045566;#14 raw_mouth_corner_vertical_asym=0.020527>=阈值0.017494 权重0.046206;#15 raw_iris_region_centroid_y_asym=0.032718>=阈值0.017457 权重0.040611;#16 raw_brow_outer_height_asym=0.058248>=阈值0.027565 权重0.039758;#17 bsdiff_eyeLookDown_abs=0.034760>=阈值0.014890 权重0.038373;#18 raw_eye_region_centroid_y_asym=0.032675>=阈值0.017110 权重0.039485;#19 raw_eyebrow_region_centroid_y_asym=0.068143>=阈值0.060332 权重0.044608 |
| pid607671849761 | new | 患病 | 0.612826 | 13 | 加权得分 0.612826 >= 阈值 0.612826；触发 13/21 个特征，触发权重 0.612826。主要原因：#2 raw_eyebrow_region_height_asym=0.138799>=阈值0.036786 权重0.047351;#4 bsdiff_browDown_abs=0.013811>=阈值0.013388 权重0.054691;#5 bsdiff_mouth_abs=0.004255>=阈值0.003855 权重0.057616;#6 bsdiff_mouth_lateral_abs=0.004255>=阈值0.003855 权重0.057616;#7 bsdiff_mouthFrown_abs=0.004259>=阈值0.000216 权重0.051817;#9 raw_eye_region_point_spread_asym=0.020246>=阈值0.010618 权重0.046633;#10 raw_eyebrow_region_point_spread_asym=0.019354>=阈值0.012080 权重0.042995;#11 raw_eyebrow_region_area_asym=0.139046>=阈值0.045246 权重0.042481;#12 raw_face_oval_region_centroid_y_asym=0.036504>=阈值0.026082 权重0.045566;#14 raw_mouth_corner_vertical_asym=0.019387>=阈值0.017494 权重0.046206;#15 raw_iris_region_centroid_y_asym=0.021409>=阈值0.017457 权重0.040611;#16 raw_brow_outer_height_asym=0.036380>=阈值0.027565 权重0.039758;#18 raw_eye_region_centroid_y_asym=0.019692>=阈值0.017110 权重0.039485 |
| pid607672731259 | new | 患病 | 0.648209 | 14 | 加权得分 0.648209 >= 阈值 0.612826；触发 14/21 个特征，触发权重 0.648209。主要原因：#1 raw_lip_midline_deviation=0.014325>=阈值0.008995 权重0.054497;#2 raw_eyebrow_region_height_asym=0.056954>=阈值0.036786 权重0.047351;#3 raw_iris_region_point_spread_asym=0.013604>=阈值0.009759 权重0.051983;#4 bsdiff_browDown_abs=0.118441>=阈值0.013388 权重0.054691;#7 bsdiff_mouthFrown_abs=0.000348>=阈值0.000216 权重0.051817;#8 raw_iris_region_area_asym=0.022859>=阈值0.019940 权重0.047742;#9 raw_eye_region_point_spread_asym=0.017512>=阈值0.010618 权重0.046633;#11 raw_eyebrow_region_area_asym=0.073570>=阈值0.045246 权重0.042481;#12 raw_face_oval_region_centroid_y_asym=0.028977>=阈值0.026082 权重0.045566;#13 bsdiff_all_mean_abs=0.059304>=阈值0.047040 权重0.047221;#15 raw_iris_region_centroid_y_asym=0.025077>=阈值0.017457 权重0.040611;#16 raw_brow_outer_height_asym=0.039902>=阈值0.027565 权重0.039758;#17 bsdiff_eyeLookDown_abs=0.204387>=阈值0.014890 权重0.038373;#18 raw_eye_region_centroid_y_asym=0.023199>=阈值0.017110 权重0.039485 |
| pid607675434444 | new | 不患病 | 0.751413 | 16 | 加权得分 0.751413 >= 阈值 0.612826；触发 16/21 个特征，触发权重 0.751413。主要原因：#1 raw_lip_midline_deviation=0.011420>=阈值0.008995 权重0.054497;#2 raw_eyebrow_region_height_asym=0.147746>=阈值0.036786 权重0.047351;#4 bsdiff_browDown_abs=0.028484>=阈值0.013388 权重0.054691;#5 bsdiff_mouth_abs=0.007974>=阈值0.003855 权重0.057616;#6 bsdiff_mouth_lateral_abs=0.007974>=阈值0.003855 权重0.057616;#7 bsdiff_mouthFrown_abs=0.000956>=阈值0.000216 权重0.051817;#8 raw_iris_region_area_asym=0.021783>=阈值0.019940 权重0.047742;#10 raw_eyebrow_region_point_spread_asym=0.017708>=阈值0.012080 权重0.042995;#11 raw_eyebrow_region_area_asym=0.144735>=阈值0.045246 权重0.042481;#12 raw_face_oval_region_centroid_y_asym=0.050709>=阈值0.026082 权重0.045566;#14 raw_mouth_corner_vertical_asym=0.019034>=阈值0.017494 权重0.046206;#15 raw_iris_region_centroid_y_asym=0.040183>=阈值0.017457 权重0.040611;#16 raw_brow_outer_height_asym=0.080489>=阈值0.027565 权重0.039758;#17 bsdiff_eyeLookDown_abs=0.029001>=阈值0.014890 权重0.038373;#18 raw_eye_region_centroid_y_asym=0.039451>=阈值0.017110 权重0.039485;#19 raw_eyebrow_region_centroid_y_asym=0.086172>=阈值0.060332 权重0.044608 |
| pid607684033107 | new | 不患病 | 0.639159 | 14 | 加权得分 0.639159 >= 阈值 0.612826；触发 14/21 个特征，触发权重 0.639159。主要原因：#2 raw_eyebrow_region_height_asym=0.116826>=阈值0.036786 权重0.047351;#3 raw_iris_region_point_spread_asym=0.013248>=阈值0.009759 权重0.051983;#7 bsdiff_mouthFrown_abs=0.000304>=阈值0.000216 权重0.051817;#8 raw_iris_region_area_asym=0.023216>=阈值0.019940 权重0.047742;#9 raw_eye_region_point_spread_asym=0.019330>=阈值0.010618 权重0.046633;#11 raw_eyebrow_region_area_asym=0.193444>=阈值0.045246 权重0.042481;#12 raw_face_oval_region_centroid_y_asym=0.050426>=阈值0.026082 权重0.045566;#15 raw_iris_region_centroid_y_asym=0.048762>=阈值0.017457 权重0.040611;#16 raw_brow_outer_height_asym=0.087179>=阈值0.027565 权重0.039758;#17 bsdiff_eyeLookDown_abs=0.036618>=阈值0.014890 权重0.038373;#18 raw_eye_region_centroid_y_asym=0.050519>=阈值0.017110 权重0.039485;#19 raw_eyebrow_region_centroid_y_asym=0.092806>=阈值0.060332 权重0.044608;#20 raw_face_oval_region_height_asym=0.021896>=阈值0.017991 权重0.051482;#21 raw_all_mesh_region_height_asym=0.021896>=阈值0.017991 权重0.051269 |
| pid607685504443 | new | 不患病 | 0.685953 | 15 | 加权得分 0.685953 >= 阈值 0.612826；触发 15/21 个特征，触发权重 0.685953。主要原因：#2 raw_eyebrow_region_height_asym=0.088315>=阈值0.036786 权重0.047351;#3 raw_iris_region_point_spread_asym=0.012020>=阈值0.009759 权重0.051983;#7 bsdiff_mouthFrown_abs=0.000266>=阈值0.000216 权重0.051817;#8 raw_iris_region_area_asym=0.024667>=阈值0.019940 权重0.047742;#11 raw_eyebrow_region_area_asym=0.059415>=阈值0.045246 权重0.042481;#12 raw_face_oval_region_centroid_y_asym=0.064657>=阈值0.026082 权重0.045566;#13 bsdiff_all_mean_abs=0.049628>=阈值0.047040 权重0.047221;#14 raw_mouth_corner_vertical_asym=0.052518>=阈值0.017494 权重0.046206;#15 raw_iris_region_centroid_y_asym=0.037784>=阈值0.017457 权重0.040611;#16 raw_brow_outer_height_asym=0.078933>=阈值0.027565 权重0.039758;#17 bsdiff_eyeLookDown_abs=0.022016>=阈值0.014890 权重0.038373;#18 raw_eye_region_centroid_y_asym=0.042095>=阈值0.017110 权重0.039485;#19 raw_eyebrow_region_centroid_y_asym=0.112898>=阈值0.060332 权重0.044608;#20 raw_face_oval_region_height_asym=0.018631>=阈值0.017991 权重0.051482;#21 raw_all_mesh_region_height_asym=0.018631>=阈值0.017991 权重0.051269 |
| pid607685976749 | new | 患病 | 0.763427 | 16 | 加权得分 0.763427 >= 阈值 0.612826；触发 16/21 个特征，触发权重 0.763427。主要原因：#1 raw_lip_midline_deviation=0.017805>=阈值0.008995 权重0.054497;#2 raw_eyebrow_region_height_asym=0.051573>=阈值0.036786 权重0.047351;#4 bsdiff_browDown_abs=0.020424>=阈值0.013388 权重0.054691;#5 bsdiff_mouth_abs=0.035927>=阈值0.003855 权重0.057616;#6 bsdiff_mouth_lateral_abs=0.035927>=阈值0.003855 权重0.057616;#7 bsdiff_mouthFrown_abs=0.001595>=阈值0.000216 权重0.051817;#11 raw_eyebrow_region_area_asym=0.059285>=阈值0.045246 权重0.042481;#12 raw_face_oval_region_centroid_y_asym=0.101075>=阈值0.026082 权重0.045566;#14 raw_mouth_corner_vertical_asym=0.067263>=阈值0.017494 权重0.046206;#15 raw_iris_region_centroid_y_asym=0.058090>=阈值0.017457 权重0.040611;#16 raw_brow_outer_height_asym=0.105699>=阈值0.027565 权重0.039758;#17 bsdiff_eyeLookDown_abs=0.017638>=阈值0.014890 权重0.038373;#18 raw_eye_region_centroid_y_asym=0.055863>=阈值0.017110 权重0.039485;#19 raw_eyebrow_region_centroid_y_asym=0.103301>=阈值0.060332 权重0.044608;#20 raw_face_oval_region_height_asym=0.023624>=阈值0.017991 权重0.051482;#21 raw_all_mesh_region_height_asym=0.023624>=阈值0.017991 权重0.051269 |
| pid607686264955 | new | 患病 | 0.915422 | 19 | 加权得分 0.915422 >= 阈值 0.612826；触发 19/21 个特征，触发权重 0.915422。主要原因：#1 raw_lip_midline_deviation=0.020997>=阈值0.008995 权重0.054497;#2 raw_eyebrow_region_height_asym=0.146146>=阈值0.036786 权重0.047351;#3 raw_iris_region_point_spread_asym=0.017644>=阈值0.009759 权重0.051983;#4 bsdiff_browDown_abs=0.106939>=阈值0.013388 权重0.054691;#5 bsdiff_mouth_abs=0.012401>=阈值0.003855 权重0.057616;#6 bsdiff_mouth_lateral_abs=0.012401>=阈值0.003855 权重0.057616;#7 bsdiff_mouthFrown_abs=0.000333>=阈值0.000216 权重0.051817;#8 raw_iris_region_area_asym=0.040691>=阈值0.019940 权重0.047742;#9 raw_eye_region_point_spread_asym=0.020799>=阈值0.010618 权重0.046633;#10 raw_eyebrow_region_point_spread_asym=0.024601>=阈值0.012080 权重0.042995;#11 raw_eyebrow_region_area_asym=0.074957>=阈值0.045246 权重0.042481;#12 raw_face_oval_region_centroid_y_asym=0.052676>=阈值0.026082 权重0.045566;#13 bsdiff_all_mean_abs=0.059189>=阈值0.047040 权重0.047221;#15 raw_iris_region_centroid_y_asym=0.043882>=阈值0.017457 权重0.040611;#16 raw_brow_outer_height_asym=0.086339>=阈值0.027565 权重0.039758;#18 raw_eye_region_centroid_y_asym=0.042847>=阈值0.017110 权重0.039485;#19 raw_eyebrow_region_centroid_y_asym=0.081682>=阈值0.060332 权重0.044608;#20 raw_face_oval_region_height_asym=0.018191>=阈值0.017991 权重0.051482;#21 raw_all_mesh_region_height_asym=0.018191>=阈值0.017991 权重0.051269 |
| pid607687423661 | new | 患病 | 0.658985 | 14 | 加权得分 0.658985 >= 阈值 0.612826；触发 14/21 个特征，触发权重 0.658985。主要原因：#1 raw_lip_midline_deviation=0.009109>=阈值0.008995 权重0.054497;#3 raw_iris_region_point_spread_asym=0.036511>=阈值0.009759 权重0.051983;#4 bsdiff_browDown_abs=0.028467>=阈值0.013388 权重0.054691;#7 bsdiff_mouthFrown_abs=0.005042>=阈值0.000216 权重0.051817;#8 raw_iris_region_area_asym=0.089764>=阈值0.019940 权重0.047742;#10 raw_eyebrow_region_point_spread_asym=0.028939>=阈值0.012080 权重0.042995;#11 raw_eyebrow_region_area_asym=0.051338>=阈值0.045246 权重0.042481;#12 raw_face_oval_region_centroid_y_asym=0.037074>=阈值0.026082 权重0.045566;#15 raw_iris_region_centroid_y_asym=0.041291>=阈值0.017457 权重0.040611;#16 raw_brow_outer_height_asym=0.072125>=阈值0.027565 权重0.039758;#18 raw_eye_region_centroid_y_asym=0.039618>=阈值0.017110 权重0.039485;#19 raw_eyebrow_region_centroid_y_asym=0.099601>=阈值0.060332 权重0.044608;#20 raw_face_oval_region_height_asym=0.028518>=阈值0.017991 权重0.051482;#21 raw_all_mesh_region_height_asym=0.028518>=阈值0.017991 权重0.051269 |

## 规范输入图片格式

- 输入单位：同一患者的一组静态人脸图片。
- 必需 role：`smile_teeth`，或旧 V1 兼容格式的 `smile + teeth`；多数高权重特征来自口部动态口径。
- 推荐 role：`front_contour/front + smile_teeth/smile,teeth + eyes_right`。
- 文件格式：`.jpg`、`.jpeg`、`.png`。
- 排除：视频、舌像、病历图、辅助检查图。
- 单图要求：清晰单人脸，正向或接近正向，嘴部、眉眼区域无遮挡，光照足够。
- MediaPipe 要求：必须能输出 `478` 个 raw landmarks、`52` 个 blendshapes、至少 1 个 facial transformation matrix。
- 推理字段：至少包含 `patient_sample_id`、`media_role`、`image_path`；训练验证时额外包含 `label_binary` 或 `label_group`。

## 产物

- 特征权重：`metadata/62_stable_weighted_feature_disease_rule_feature_weights.csv`
- 加权分阈值：`metadata/62_stable_weighted_feature_disease_rule_score_threshold.csv`
- 患者判断：`metadata/62_stable_weighted_feature_disease_rule_patient_predictions.csv`
- 患者特征贡献：`metadata/62_stable_weighted_feature_disease_rule_patient_feature_contributions.csv`
- 指标：`metadata/62_stable_weighted_feature_disease_rule_metrics.csv`
- JSON 摘要：`metadata/62_stable_weighted_feature_disease_rule_summary.json`

## 限制

该规则使用患者 outcome 弱标签拟合，只能作为技术判断与归因候选，不能作为临床诊断结论。
