# Face-video-first diabetes risk project correction

Use this reference when managing the user's diabetes / face-health project or any similar project whose stated product goal is “扫脸看健康”.

## Durable project-goal lesson

If the user states the final goal is “通过人脸视频端到端完成糖尿病风险评估”, treat that as a fixed product objective, not as an experiment that may be replaced by a health-record model.

Correct framing:

```text
Final product line: face-video-first diabetes risk assessment.
Health records, glucose, HbA1c, questionnaires, and rule scores support training supervision, label construction, calibration, interpretation, and control/baseline comparisons.
```

Avoid drifting into:

```text
Health-profile model is the product mainline; face/rPPG is merely optional auxiliary.
```

## PM workflow implications

1. When summarizing project status, lead with the fixed product goal:
   - “扫脸看健康：以人脸视频为核心输入，端到端完成糖尿病风险评估。”
2. Treat MCD-rPPG, ROI extraction, rPPG, facial color, landmark quality, and video quality control as mainline evidence-building tasks, not side quests.
3. Health-record baselines remain valuable, but label them as:
   - teacher / baseline / calibration / clinical context / interpretability / validation reference.
4. Do not propose “downgrading” the project to a pure tabular health-profile product unless the user explicitly changes the fixed goal.
5. Preserve clinical caveats: face-video risk assessment is not diagnosis; it cannot claim camera glucose or HbA1c measurement.

## Recommended next-step language

Prefer:

```text
Next step: expand face-video evidence — more MCD-rPPG subjects, longer ROI/rPPG windows, subject-level split, and shallow risk-model smoke validation.
```

Avoid:

```text
Next step: build health-profile schema first; visual branch is optional.
```

## Documentation hygiene

When generating project documents, explicitly separate:

- Fixed product goal: face-video end-to-end risk assessment.
- Supporting supervision/calibration context: health records, HbA1c, glucose, questionnaire/rule scores.
- Clinical safety boundary: risk assessment only, not diagnosis.
