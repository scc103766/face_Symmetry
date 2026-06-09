from __future__ import annotations

from scripts.extract_v11_grade_v_plus_nondisease_review import compact_features, role_driver_labels


def test_compact_features_deduplicates_and_limits_terms() -> None:
    raw = "raw_a;raw_b,raw_a;raw_c;raw_d"

    assert compact_features(raw, limit=3) == ["raw_a", "raw_b", "raw_c"]


def test_role_driver_labels_keep_high_scoring_roles_only() -> None:
    rows = {
        "front": {"role_asymmetry_score": "0.540000", "top_positive_features": "raw_front"},
        "smile": {"role_asymmetry_score": "0.750000", "top_positive_features": "raw_smile;raw_mouth"},
        "frown": {"role_asymmetry_score": "0.600000", "top_positive_features": "raw_brow"},
    }

    labels = role_driver_labels(rows)

    assert len(labels) == 2
    assert labels[0].startswith("微笑(")
    assert labels[1].startswith("皱眉(")
    assert all(not label.startswith("正脸静息(") for label in labels)
