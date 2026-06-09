#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_by_name_20260119"
CORE_ROLES = ("front", "smile", "teeth")


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    metadata = dataset / "metadata"
    reports = dataset / "reports"

    full_rows = read_csv(metadata / "09_mediapipe_full_features.csv")
    split_rows = read_csv(metadata / "05_patient_splits.csv")
    split_by_patient = {row["patient_sample_id"]: row["split"] for row in split_rows}
    for row in full_rows:
        row["split"] = split_by_patient.get(row["patient_sample_id"], "")

    feature_set = build_feature_set(full_rows, min_separation_auc=args.min_separation_auc)
    image_scores = score_images(full_rows, feature_set)
    patient_scores = score_patients(image_scores)
    predictions, threshold = evaluate_patient_scores(patient_scores)
    evaluation = build_evaluation(predictions, threshold, feature_set, image_scores, patient_scores)

    write_csv(metadata / "10_weak_association_feature_set.csv", feature_set)
    write_csv(metadata / "10_weak_association_image_scores.csv", image_scores)
    write_csv(metadata / "10_weak_association_patient_scores.csv", patient_scores)
    write_csv(metadata / "10_weak_association_predictions.csv", predictions)
    write_json(metadata / "10_weak_association_evaluation.json", evaluation)
    write_report(reports / "10_weak_association_stacked_score.md", evaluation, feature_set)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build V1.1 weak-association stacked asymmetry score.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="FaceSymAi V1 dataset root.")
    parser.add_argument(
        "--min-separation-auc",
        type=float,
        default=0.53,
        help="Minimum train split separation AUC for a weakly associated asymmetry feature.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    fixed = [
        "patient_sample_id",
        "sample_id",
        "label_group",
        "label_binary",
        "split",
        "media_role",
        "role",
        "feature_name",
    ]
    fields = [field for field in fixed if field in fields] + [field for field in fields if field not in fixed]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def is_asymmetry_feature(name: str) -> bool:
    if name.startswith("bsdiff_"):
        return True
    return name.startswith("raw_") and ("asym" in name or "deviation" in name)


def build_feature_set(rows: list[dict[str, str]], *, min_separation_auc: float) -> list[dict[str, Any]]:
    feature_names = sorted(
        key
        for key in rows[0]
        if is_asymmetry_feature(key)
    )
    output: list[dict[str, Any]] = []
    train_rows = [row for row in rows if row.get("split") == "train"]
    for role in CORE_ROLES:
        role_rows = [row for row in train_rows if row.get("media_role") == role]
        for feature_name in feature_names:
            pos = values_for(role_rows, feature_name, "1")
            neg = values_for(role_rows, feature_name, "0")
            if len(pos) < 20 or len(neg) < 20:
                continue
            positive_mean = mean(pos)
            negative_mean = mean(neg)
            score_auc = auc_positive_higher(pos, neg)
            separation_auc = max(score_auc, 1.0 - score_auc)
            if separation_auc < min_separation_auc:
                continue
            all_values = pos + neg
            train_mean = mean(all_values)
            train_std = std(all_values)
            if train_std <= 1e-12:
                continue
            direction = 1.0 if positive_mean >= negative_mean else -1.0
            effect = cohens_d(pos, neg)
            # Weight weak signals gently. AUC distance from 0.5 controls ranking signal;
            # effect size controls mean separation without letting one noisy feature dominate.
            weight = max(0.0, separation_auc - 0.5) * max(0.05, min(abs(effect), 0.75))
            output.append(
                {
                    "role": role,
                    "feature_name": feature_name,
                    "positive_n": len(pos),
                    "negative_n": len(neg),
                    "positive_mean": fmt(positive_mean),
                    "negative_mean": fmt(negative_mean),
                    "direction_positive_higher": "1" if direction > 0 else "0",
                    "train_mean": fmt(train_mean),
                    "train_std": fmt(train_std),
                    "cohens_d": fmt(effect),
                    "auc_positive_higher": fmt(score_auc),
                    "separation_auc": fmt(separation_auc),
                    "weight": fmt(weight),
                    "selection_rule": f"asymmetry_candidate && train_separation_auc>={min_separation_auc:.2f}",
                }
            )
    return sorted(output, key=lambda row: (row["role"], -float(row["weight"]), row["feature_name"]))


def values_for(rows: list[dict[str, str]], feature_name: str, label: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        if row.get("label_binary") != label:
            continue
        value = parse_float(row.get(feature_name, ""))
        if value is not None:
            values.append(value)
    return values


def score_images(rows: list[dict[str, str]], feature_set: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features_by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for feature in feature_set:
        features_by_role[feature["role"]].append(feature)

    output: list[dict[str, Any]] = []
    for row in rows:
        role = row["media_role"]
        selected = features_by_role.get(role, [])
        weighted_sum = 0.0
        weight_total = 0.0
        contributions: list[tuple[float, str]] = []
        for feature in selected:
            value = parse_float(row.get(feature["feature_name"], ""))
            if value is None:
                continue
            train_mean = float(feature["train_mean"])
            train_std = float(feature["train_std"])
            direction = 1.0 if feature["direction_positive_higher"] == "1" else -1.0
            weight = float(feature["weight"])
            aligned_z = direction * ((value - train_mean) / train_std)
            contribution = weight * aligned_z
            weighted_sum += contribution
            weight_total += weight
            contributions.append((contribution, feature["feature_name"]))
        stacked_z = weighted_sum / weight_total if weight_total > 0 else 0.0
        score = sigmoid(stacked_z)
        output.append(
            {
                "sample_id": row["sample_id"],
                "patient_sample_id": row["patient_sample_id"],
                "label_group": row["label_group"],
                "label_binary": row["label_binary"],
                "split": row["split"],
                "media_role": role,
                "weak_feature_terms": len(contributions),
                "weak_weight_total": fmt(weight_total),
                "weak_stacked_z": fmt(stacked_z),
                "weak_association_score": fmt(score),
                "top_positive_terms": ";".join(name for _value, name in sorted(contributions, reverse=True)[:5]),
                "top_negative_terms": ";".join(name for _value, name in sorted(contributions)[:5]),
            }
        )
    return output


def score_patients(image_scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in image_scores:
        grouped[row["patient_sample_id"]].append(row)

    output: list[dict[str, Any]] = []
    for patient_id, rows in sorted(grouped.items()):
        core_rows = [row for row in rows if row["media_role"] in CORE_ROLES]
        weighted_sum = 0.0
        weight_total = 0.0
        role_scores: dict[str, str] = {}
        for row in core_rows:
            role = row["media_role"]
            z = float(row["weak_stacked_z"])
            weight = float(row["weak_weight_total"])
            weighted_sum += z * weight
            weight_total += weight
            role_scores[role] = row["weak_association_score"]
        stacked_z = weighted_sum / weight_total if weight_total > 0 else 0.0
        score = sigmoid(stacked_z)
        first = rows[0]
        output_row: dict[str, Any] = {
            "patient_sample_id": patient_id,
            "label_group": first["label_group"],
            "label_binary": first["label_binary"],
            "split": first["split"],
            "roles_available": len(core_rows),
            "weak_feature_terms": sum(int(row["weak_feature_terms"]) for row in core_rows),
            "weak_weight_total": fmt(weight_total),
            "weak_stacked_z": fmt(stacked_z),
            "weak_association_score": fmt(score),
        }
        for role in CORE_ROLES:
            output_row[f"{role}_weak_association_score"] = role_scores.get(role, "")
        output.append(output_row)
    return output


def evaluate_patient_scores(patient_scores: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
    val_rows = [row for row in patient_scores if row["split"] == "val"]
    thresholds = sorted({float(row["weak_association_score"]) for row in val_rows})
    if not thresholds:
        threshold = 0.5
    else:
        threshold = max(
            thresholds,
            key=lambda item: (
                binary_metrics(val_rows, item)["balanced_accuracy"],
                binary_metrics(val_rows, item)["precision"],
                binary_metrics(val_rows, item)["recall"],
            ),
        )

    predictions: list[dict[str, Any]] = []
    for row in patient_scores:
        score = float(row["weak_association_score"])
        pred = "1" if score >= threshold else "0"
        predictions.append(
            {
                **row,
                "threshold": fmt(threshold),
                "predicted_positive": pred,
                "confusion_cell": confusion_cell(row["label_binary"], pred),
            }
        )
    return predictions, threshold


def build_evaluation(
    predictions: list[dict[str, Any]],
    threshold: float,
    feature_set: list[dict[str, Any]],
    image_scores: list[dict[str, Any]],
    patient_scores: list[dict[str, Any]],
) -> dict[str, Any]:
    metrics = {
        split: binary_metrics([row for row in predictions if row["split"] == split], threshold=None)
        for split in ["train", "val", "test"]
    }
    aucs = {
        split: patient_auc([row for row in patient_scores if row["split"] == split])
        for split in ["train", "val", "test"]
    }
    operating_points = build_operating_points(patient_scores)
    return {
        "version": "v1.1_weak_association_stacked_score",
        "score_definition": "Sum train-selected weak asymmetry associations after disease-direction alignment and train z-score normalization.",
        "feature_selection": {
            "source": "metadata/09_mediapipe_full_features.csv",
            "roles": list(CORE_ROLES),
            "candidate_rule": "bsdiff_* OR raw_* containing asym/deviation",
            "split_for_selection": "train",
            "min_train_separation_auc": min(float(row["separation_auc"]) for row in feature_set) if feature_set else None,
            "selected_features": len(feature_set),
            "selected_by_role": dict(count_by(feature_set, "role")),
        },
        "threshold_source": "validation split, maximize balanced accuracy then precision then recall",
        "threshold": threshold,
        "metrics": metrics,
        "auc": aucs,
        "operating_points": operating_points,
        "image_scores": len(image_scores),
        "patient_scores": len(patient_scores),
        "warning": "This is a weak-association technical score against patient outcome labels, not a direct clinical diagnostic score.",
    }


def build_operating_points(patient_scores: list[dict[str, Any]]) -> dict[str, Any]:
    val_rows = [row for row in patient_scores if row["split"] == "val"]
    thresholds = sorted({float(row["weak_association_score"]) for row in val_rows})
    definitions = {
        "balanced_accuracy": lambda m: (m["balanced_accuracy"], m["precision"], m["recall"]),
        "recall_ge_0.90": lambda m: (m["specificity"], m["precision"], m["balanced_accuracy"]) if m["recall"] >= 0.90 else None,
        "precision_ge_0.75": lambda m: (m["recall"], m["specificity"], m["balanced_accuracy"]) if m["precision"] >= 0.75 else None,
    }
    output: dict[str, Any] = {}
    for name, scorer in definitions.items():
        candidates: list[tuple[tuple[float, ...], float]] = []
        for threshold in thresholds:
            score = scorer(binary_metrics(val_rows, threshold))
            if score is not None:
                candidates.append((score, threshold))
        if not candidates:
            output[name] = {"available": False}
            continue
        threshold = max(candidates, key=lambda item: item[0])[1]
        output[name] = {
            "available": True,
            "threshold": threshold,
            "val": binary_metrics([row for row in patient_scores if row["split"] == "val"], threshold),
            "test": binary_metrics([row for row in patient_scores if row["split"] == "test"], threshold),
        }
    return output


def binary_metrics(rows: list[Mapping[str, Any]], threshold: float | None) -> dict[str, Any]:
    tp = fp = tn = fn = skipped = 0
    for row in rows:
        truth = str(row.get("label_binary", ""))
        if threshold is None:
            pred = str(row.get("predicted_positive", ""))
        else:
            pred = "1" if float(row["weak_association_score"]) >= threshold else "0"
        if truth not in {"0", "1"} or pred not in {"0", "1"}:
            skipped += 1
            continue
        if truth == "1" and pred == "1":
            tp += 1
        elif truth == "0" and pred == "1":
            fp += 1
        elif truth == "0" and pred == "0":
            tn += 1
        elif truth == "1" and pred == "0":
            fn += 1
    evaluated = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    accuracy = (tp + tn) / evaluated if evaluated else 0.0
    balanced = (recall + specificity) / 2.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "patients": len(rows),
        "evaluated": evaluated,
        "skipped": skipped,
        "accuracy": accuracy,
        "balanced_accuracy": balanced,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def patient_auc(rows: list[Mapping[str, Any]]) -> float:
    pos = [float(row["weak_association_score"]) for row in rows if row.get("label_binary") == "1"]
    neg = [float(row["weak_association_score"]) for row in rows if row.get("label_binary") == "0"]
    if not pos or not neg:
        return 0.0
    return auc_positive_higher(pos, neg)


def confusion_cell(truth: str, pred: str) -> str:
    if truth == "1" and pred == "1":
        return "tp"
    if truth == "0" and pred == "1":
        return "fp"
    if truth == "0" and pred == "0":
        return "tn"
    if truth == "1" and pred == "0":
        return "fn"
    return "skipped"


def count_by(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
    output: dict[str, int] = defaultdict(int)
    for row in rows:
        output[str(row[key])] += 1
    return dict(sorted(output.items()))


def parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    if not math.isfinite(result):
        return None
    return result


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def std(values: list[float]) -> float:
    m = mean(values)
    return math.sqrt(sum((value - m) ** 2 for value in values) / len(values))


def cohens_d(pos: list[float], neg: list[float]) -> float:
    pos_mean = mean(pos)
    neg_mean = mean(neg)
    pooled = math.sqrt((std(pos) ** 2 + std(neg) ** 2) / 2.0)
    return (pos_mean - neg_mean) / pooled if pooled > 1e-12 else 0.0


def auc_positive_higher(pos: list[float], neg: list[float]) -> float:
    combined = sorted([(value, 1) for value in pos] + [(value, 0) for value in neg], key=lambda item: item[0])
    rank_sum_pos = 0.0
    index = 0
    while index < len(combined):
        end = index + 1
        while end < len(combined) and combined[end][0] == combined[index][0]:
            end += 1
        avg_rank = (index + 1 + end) / 2.0
        for item_index in range(index, end):
            if combined[item_index][1] == 1:
                rank_sum_pos += avg_rank
        index = end
    n_pos = len(pos)
    n_neg = len(neg)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def fmt(value: float) -> str:
    return f"{value:.6f}"


def write_report(path: Path, evaluation: Mapping[str, Any], feature_set: list[dict[str, Any]]) -> None:
    lines = [
        "# 10 V1.1 弱关联叠加评分",
        "",
        "分析对象：`datasets/facesym_v1_by_name_20260119`",
        "",
        "## 目标",
        "",
        "这个版本把“人脸不对称性判断”定义为：从 MediaPipe 478 raw landmarks 和 52 blendshape 中筛出与 `患病/不患病` 存在弱关联的左右不对称项，将这些弱关联项按患病方向对齐后叠加。",
        "",
        "这里的核心假设是：单个特征都很弱，但多个弱关联项叠加后，可以形成一个更稳定的 disease-like facial asymmetry score。它仍然不是临床诊断分数，也不是直接面瘫标注训练出的模型。",
        "",
        "## 评分口径",
        "",
        "- 候选特征：`bsdiff_*`，以及包含 `asym/deviation` 的 `raw_*` 特征。",
        "- 排除项：matrix 平移/尺度、`raw_eye_distance` 等采集距离或姿态相关特征不进入主评分。",
        "- 特征选择：只用 train split，按 role 分别选择 train separation AUC >= 0.53 的弱关联项。",
        "- 方向对齐：如果患病均值更高，则 z-score 原方向计入；如果不患病均值更高，则取反后计入。",
        "- 标准化：使用 train split 的均值和标准差。",
        "- 加权：`(separation_auc - 0.5) * clipped_abs(cohens_d)`。",
        "- 患者聚合：把 front/smile/teeth 的所有弱关联项按权重汇总，不使用单图 max。",
        "",
        "## 产物",
        "",
        "- Feature set: `metadata/10_weak_association_feature_set.csv`",
        "- Image scores: `metadata/10_weak_association_image_scores.csv`",
        "- Patient scores: `metadata/10_weak_association_patient_scores.csv`",
        "- Predictions: `metadata/10_weak_association_predictions.csv`",
        "- Evaluation JSON: `metadata/10_weak_association_evaluation.json`",
        "",
        "## 特征数量",
        "",
        f"- Selected features: `{evaluation['feature_selection']['selected_features']}`",
        f"- Selected by role: `{json.dumps(evaluation['feature_selection']['selected_by_role'], ensure_ascii=False, sort_keys=True)}`",
        "",
        "## 评估结果",
        "",
        f"- Threshold source: `{evaluation['threshold_source']}`",
        f"- Threshold: `{evaluation['threshold']:.6f}`",
        "",
        "| split | patients | accuracy | balanced_accuracy | precision | recall | specificity | auc | tp | fp | tn | fn |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for split in ["train", "val", "test"]:
        metrics = evaluation["metrics"][split]
        lines.append(
            "| {split} | {patients} | {accuracy:.6f} | {balanced_accuracy:.6f} | {precision:.6f} | {recall:.6f} | {specificity:.6f} | {auc:.6f} | {tp} | {fp} | {tn} | {fn} |".format(
                split=split,
                auc=evaluation["auc"][split],
                **metrics,
            )
        )
    lines.extend(
        [
            "",
            "## 阈值操作点",
            "",
            "| strategy | threshold | val_precision | val_recall | val_specificity | test_precision | test_recall | test_specificity | test_balanced_accuracy |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, payload in evaluation["operating_points"].items():
        if not payload.get("available"):
            continue
        val_metrics = payload["val"]
        test_metrics = payload["test"]
        lines.append(
            "| {name} | {threshold:.6f} | {val_precision:.6f} | {val_recall:.6f} | {val_specificity:.6f} | {test_precision:.6f} | {test_recall:.6f} | {test_specificity:.6f} | {test_balanced_accuracy:.6f} |".format(
                name=name,
                threshold=payload["threshold"],
                val_precision=val_metrics["precision"],
                val_recall=val_metrics["recall"],
                val_specificity=val_metrics["specificity"],
                test_precision=test_metrics["precision"],
                test_recall=test_metrics["recall"],
                test_specificity=test_metrics["specificity"],
                test_balanced_accuracy=test_metrics["balanced_accuracy"],
            )
        )
    lines.extend(
        [
            "",
            "## 权重最高的弱关联项",
            "",
            *feature_table(feature_set[:30]),
            "",
            "## 解释",
            "",
            "这个版本的意义是把当前数据中分散的弱信号收拢成一个可复跑分数。若 test 上的 balanced accuracy 或 AUC 仍然有限，说明 patient outcome 标签对人脸不对称的监督仍然很弱；下一步应接入人工不对称标注，而不是继续只用患病标签调权重。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def feature_table(rows: list[dict[str, Any]]) -> list[str]:
    output = [
        "| role | feature | pos_mean | neg_mean | d | auc | sep_auc | weight | direction |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        direction = "患病更高" if row["direction_positive_higher"] == "1" else "不患病更高"
        output.append(
            "| {role} | {feature_name} | {positive_mean} | {negative_mean} | {cohens_d} | {auc_positive_higher} | {separation_auc} | {weight} | {direction} |".format(
                direction=direction,
                **row,
            )
        )
    return output


if __name__ == "__main__":
    main()
