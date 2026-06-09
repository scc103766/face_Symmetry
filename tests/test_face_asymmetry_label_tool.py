from __future__ import annotations

import pytest

from scripts.serve_face_asymmetry_label_tool import (
    FaceAsymmetryLabelApp,
    LABEL_NAME,
    TEMPLATE_NAME,
    access_urls,
    dataset_url,
    read_csv_with_fields,
    safe_join,
    save_label_payload,
    write_csv,
)


def make_dataset(tmp_path):
    dataset = tmp_path / "dataset"
    metadata = dataset / "metadata"
    metadata.mkdir(parents=True)
    fields = [
        "patient_sample_id",
        "split",
        "label_group",
        "label_binary",
        "hb_proxy_grade",
        "hb_proxy_grade_num",
        "face_asymmetry_output",
        "manual_face_asymmetry_label",
        "manual_asymmetry_grade",
        "quality_review_usable_for_calibration",
        "quality_review_label",
        "review_source",
        "reviewer_id",
        "review_date",
        "review_notes",
        "review_priority",
        "front_annotation_path",
        "smile_annotation_path",
        "resting_symmetry_score",
        "eye_closure_score",
        "brow_forehead_score",
        "smile_mouth_score",
        "gross_asymmetry_score",
        "movement_absence_score",
        "hb_proxy_overall_score",
        "hb_grade_confidence",
        "face_asymmetry_reason",
        "hb_reason_codes",
    ]
    rows = [
        {
            "patient_sample_id": "p1",
            "split": "test",
            "label_group": "不患病",
            "label_binary": "0",
            "hb_proxy_grade": "Grade V",
            "hb_proxy_grade_num": "5",
            "face_asymmetry_output": "人脸不对称",
            "review_priority": "p0_grade_v_plus_nondisease_false_positive_review",
            "front_annotation_path": "annotated/p1/front.jpg",
            "smile_annotation_path": "annotated/p1/smile.jpg",
            "resting_symmetry_score": "0.600000",
            "hb_proxy_overall_score": "0.700000",
            "face_asymmetry_reason": "reason",
            "hb_reason_codes": "code",
        },
        {
            "patient_sample_id": "p2",
            "split": "train",
            "label_group": "患病",
            "label_binary": "1",
            "hb_proxy_grade": "Grade II",
            "hb_proxy_grade_num": "2",
            "review_priority": "p1_diseased_low_grade_review",
        },
    ]
    write_csv(metadata / TEMPLATE_NAME, rows, fields)
    return dataset


def test_save_label_payload_writes_review_label_file(tmp_path) -> None:
    dataset = make_dataset(tmp_path)
    template = dataset / "metadata" / TEMPLATE_NAME
    labels = dataset / "metadata" / LABEL_NAME

    saved = save_label_payload(
        template,
        labels,
        {
            "patient_sample_id": "p1",
            "manual_face_asymmetry_label": "1",
            "manual_asymmetry_grade": "5",
            "quality_review_usable_for_calibration": "1",
            "quality_review_label": "可用",
            "reviewer_id": "reviewer-a",
            "review_notes": "right mouth corner lower",
        },
    )
    rows, fields = read_csv_with_fields(labels)

    assert saved["patient_sample_id"] == "p1"
    assert "manual_face_asymmetry_label" in fields
    assert len(rows) == 2
    assert rows[0]["manual_face_asymmetry_label"] == "1"
    assert rows[0]["manual_asymmetry_grade"] == "5"
    assert rows[0]["review_source"] == "html_label_tool"
    assert rows[1]["manual_face_asymmetry_label"] == ""


def test_case_payload_merges_existing_labels_and_counts_summary(tmp_path) -> None:
    dataset = make_dataset(tmp_path)
    template = dataset / "metadata" / TEMPLATE_NAME
    labels = dataset / "metadata" / LABEL_NAME
    save_label_payload(
        template,
        labels,
        {
            "patient_sample_id": "p1",
            "manual_face_asymmetry_label": "0",
            "manual_asymmetry_grade": "1",
            "quality_review_usable_for_calibration": "1",
        },
    )

    payload = FaceAsymmetryLabelApp(dataset, tmp_path / "page.html").case_payload()

    assert payload["summary"]["labeled"] == 1
    assert payload["summary"]["negative"] == 1
    assert payload["cases"][0]["status"] == "labeled"
    assert payload["cases"][0]["images"][0]["url"] == "/dataset/annotated/p1/front.jpg"


def test_quality_rejected_payload_is_excluded_from_unlabeled_count(tmp_path) -> None:
    dataset = make_dataset(tmp_path)
    template = dataset / "metadata" / TEMPLATE_NAME
    labels = dataset / "metadata" / LABEL_NAME

    save_label_payload(
        template,
        labels,
        {
            "patient_sample_id": "p2",
            "quality_review_usable_for_calibration": "0",
            "quality_review_label": "",
        },
    )
    payload = FaceAsymmetryLabelApp(dataset, tmp_path / "page.html").case_payload(status="quality_rejected")

    assert payload["summary"]["quality_rejected"] == 1
    assert payload["summary"]["unlabeled"] == 1
    assert payload["filtered"] == 1
    assert payload["cases"][0]["label"]["quality_review_label"] == "人工复核不可用"


def test_invalid_manual_grade_is_rejected(tmp_path) -> None:
    dataset = make_dataset(tmp_path)

    with pytest.raises(ValueError, match="manual_asymmetry_grade"):
        save_label_payload(
            dataset / "metadata" / TEMPLATE_NAME,
            dataset / "metadata" / LABEL_NAME,
            {"patient_sample_id": "p1", "manual_asymmetry_label": "1", "manual_asymmetry_grade": "7"},
        )


def test_safe_join_blocks_dataset_path_traversal(tmp_path) -> None:
    dataset = make_dataset(tmp_path)

    assert safe_join(dataset, "annotated/p1/front.jpg") == (dataset / "annotated/p1/front.jpg").resolve()
    assert safe_join(dataset, "../outside.jpg") is None


def test_access_token_is_added_to_remote_urls_and_image_urls(tmp_path) -> None:
    dataset = make_dataset(tmp_path)

    payload = FaceAsymmetryLabelApp(dataset, tmp_path / "page.html", access_token="secret token").case_payload()
    urls = access_urls("0.0.0.0", 8765, "secret token", "https://example.org/facesym")

    assert payload["cases"][0]["images"][0]["url"].endswith("?token=secret%20token")
    assert dataset_url("annotated/p1/front.jpg", "secret token") == "/dataset/annotated/p1/front.jpg?token=secret%20token"
    assert "https://example.org/facesym/?token=secret%20token" in urls
    assert "http://127.0.0.1:8765/?token=secret%20token" in urls


def test_access_token_authorizes_header_or_query(tmp_path) -> None:
    class Request:
        def __init__(self, headers):
            self.headers = headers

    app = FaceAsymmetryLabelApp(make_dataset(tmp_path), tmp_path / "page.html", access_token="secret")

    assert app.authorized(Request({"X-Label-Tool-Token": "secret"}), "")
    assert app.authorized(Request({}), "token=secret")
    assert not app.authorized(Request({"X-Label-Tool-Token": "wrong"}), "")
