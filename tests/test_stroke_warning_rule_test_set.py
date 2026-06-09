from __future__ import annotations

from scripts.build_stroke_warning_rule_test_set import (
    BASE_DISEASE_FIELD,
    EXERCISE_FIELD,
    FAMILY_STROKE_FIELD,
    NUMBNESS_FIELD,
    OVERWEIGHT_FIELD,
    PRIOR_STROKE_FIELD,
    RISK_FIELD,
    SMOKE_FIELD,
    WEAKNESS_FIELD,
    RuleRecord,
    build_record_rows,
    decide_patients,
    is_all_normal_low_risk,
    positive_reasons,
    record_id_for,
)


def normal_low_risk_row() -> dict[str, str]:
    return {
        RISK_FIELD: "低风险",
        BASE_DISEASE_FIELD: "无",
        SMOKE_FIELD: "无",
        EXERCISE_FIELD: "是",
        OVERWEIGHT_FIELD: "否",
        WEAKNESS_FIELD: "无",
        NUMBNESS_FIELD: "无",
        PRIOR_STROKE_FIELD: "否",
        FAMILY_STROKE_FIELD: "无",
    }


def rule_record(patient_id: str, excel_row: int, row: dict[str, str]) -> RuleRecord:
    return RuleRecord(
        record_id=record_id_for(excel_row, patient_id),
        source_excel_row=excel_row,
        patient_id=patient_id,
        row=row,
        positive_reasons=positive_reasons(row),
        is_normal_negative=is_all_normal_low_risk(row),
    )


def test_positive_rules_accept_emergency_prior_and_family_stroke() -> None:
    row = normal_low_risk_row()
    row[RISK_FIELD] = "紧急风险"
    row[PRIOR_STROKE_FIELD] = "是"
    row[FAMILY_STROKE_FIELD] = "有"

    reasons = positive_reasons(row)

    assert reasons == ["risk_level_emergency", "prior_stroke_yes", "family_stroke_yes"]


def test_positive_rules_reject_single_condition_matches() -> None:
    emergency_only = normal_low_risk_row()
    emergency_only[RISK_FIELD] = "紧急风险"
    prior_only = normal_low_risk_row()
    prior_only[PRIOR_STROKE_FIELD] = "是"
    family_only = normal_low_risk_row()
    family_only[FAMILY_STROKE_FIELD] = "有"

    assert positive_reasons(emergency_only) == []
    assert positive_reasons(prior_only) == []
    assert positive_reasons(family_only) == []


def test_low_risk_all_indicators_normal_is_negative_candidate() -> None:
    assert is_all_normal_low_risk(normal_low_risk_row())


def test_low_risk_with_any_abnormal_indicator_is_not_negative_candidate() -> None:
    row = normal_low_risk_row()
    row[SMOKE_FIELD] = "有"

    assert not is_all_normal_low_risk(row)
    assert positive_reasons(row) == []


def test_patient_positive_precedence_over_low_risk_normal_record() -> None:
    normal_row = normal_low_risk_row()
    positive_row = normal_low_risk_row()
    positive_row[RISK_FIELD] = "紧急风险"
    positive_row[PRIOR_STROKE_FIELD] = "是"
    positive_row[FAMILY_STROKE_FIELD] = "有"
    records = [
        rule_record("607688041677", 428, normal_row),
        rule_record("607688041677", 429, positive_row),
    ]

    decisions = decide_patients(records)
    selected_rows, excluded_rows = build_record_rows(decisions)
    decision = decisions["607688041677"]

    assert decision.label_group == "患病"
    assert [record.source_excel_row for record in decision.selected_records] == [429]
    assert selected_rows[0]["label_binary"] == "1"
    assert excluded_rows[0]["exclude_reason"] == "patient_positive_precedence_over_normal_record"
