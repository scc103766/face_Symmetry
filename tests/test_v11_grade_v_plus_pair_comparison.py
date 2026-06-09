from __future__ import annotations

from scripts.compare_v11_grade_v_plus_18_disease_nondisease import match_diseased_cases


def test_match_diseased_cases_prefers_complete_core_role_images() -> None:
    nondisease = [
        {
            "patient_sample_id": "nondisease-1",
            "split": "test",
            "hb_proxy_grade_num": "5",
            "hb_proxy_overall_score": "0.600000",
        }
    ]
    diseased = [
        {
            "patient_sample_id": "diseased-incomplete",
            "split": "test",
            "hb_proxy_grade_num": "5",
            "hb_proxy_overall_score": "0.600100",
            "annotation_paths": "front.jpg;smile.jpg",
        },
        {
            "patient_sample_id": "diseased-complete",
            "split": "test",
            "hb_proxy_grade_num": "5",
            "hb_proxy_overall_score": "0.620000",
            "annotation_paths": "front.jpg;smile.jpg;teeth.jpg;eyes.jpg;forehead.jpg;frown.jpg",
        },
    ]

    pairs = match_diseased_cases(nondisease, diseased)

    assert pairs[0]["matching_rule"] == "same_split_same_grade_closest_score"
    assert pairs[0]["diseased"]["patient_sample_id"] == "diseased-complete"
