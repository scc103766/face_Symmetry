# Flash Liveness Attack Research Documentation Workflow

Use this reference when a PM-mode user asks for literature/technical/open-source research for a face liveness / face anti-spoofing project, especially when the project combines active flash challenge-response with RGB video.

## Trigger

- User asks to检索/整理 papers, open-source projects, technical routes for face liveness, PAD, anti-spoofing, deepfake, AI换脸.
- User wants separate Markdown files and engineering-oriented recommendations.
- Project already has a PM skeleton (`PROJECT_CONTEXT.md`, `WORK_STATUS.md`, `tasks/`, `sessions/`).

## PM sequence

1. Read `PROJECT_CONTEXT.md` and `WORK_STATUS.md` first.
2. Identify the current fixed baseline before writing recommendations:
   - active protocol version,
   - current model/checkpoint family,
   - face detector/alignment pipeline,
   - API/service entrypoint,
   - GPU/environment policy.
3. Propose the research document structure and wait for explicit approval before creating files.
4. After approval, split research into at least three workstreams:
   - traditional PAD / presentation attacks,
   - AI face-swap / deepfake / face forgery,
   - current-project integration and upgrade recommendations.
5. Prefer research documents that are actionable for engineering, not paper dumps.
6. If external search is incomplete, label the limitation clearly and mark license/weights/data availability as “需复核”; do not invent verified status.
7. Write a completion report under `tasks/done/<task_id>_report.md` and update `WORK_STATUS.md`/`PROJECT_CONTEXT.md`.

## Recommended document layout

Create a class-level research folder such as:

```text
docs/flash_liveness/research/
├── README.md
├── TRADITIONAL_FACE_PRESENTATION_ATTACKS.md
├── AI_DEEPFAKE_FACE_ATTACKS.md
├── OPEN_SOURCE_PROJECTS_SURVEY.md
├── PAPERS_SUMMARY.md
└── UPGRADE_RECOMMENDATIONS_FOR_AI_FACE_SWAP.md
```

## Content rubric

For traditional PAD:

- photo/print attacks,
- replay/screen attacks,
- mask attacks,
- 3D mask/head model attacks,
- datasets and protocols: Replay-Attack, CASIA-FASD, MSU-MFSD, OULU-NPU, SiW/SiW-M, CelebA-Spoof, 3DMAD, HKBU-MARs, WMCA,
- techniques: LBP/color texture, dynamic texture, DeepPixBiS, CDCN, pseudo-depth, FFT/frequency supervision, rPPG/physiology, active challenge-response.

For AI face-swap/deepfake:

- FaceSwap, face reenactment, lip-sync, GAN/diffusion generated faces, deepfake replay,
- datasets: FaceForensics++, Celeb-DF, DFDC, DeeperForensics, WildDeepfake, FakeAVCeleb,
- techniques: Xception/EfficientNet baselines, Face X-Ray/blending boundary, F3-Net/frequency clues, LipForensics/mouth ROI, temporal coherence, AltFreezing, rPPG/physiology, diffusion-generated image detection.

For current-project recommendations:

- preserve the active flash challenge-response baseline;
- add, do not replace with, a `deepfake_score`/face-swap head;
- add `protocol_consistency_score` for txt/video/flash alignment;
- add ROI tokens for eye/mouth/cheek/boundary regions;
- extend frequency features from global FFT to local ROI FFT/DCT/wavelet/high-frequency residual;
- report `AI-APCER`, `Traditional-APCER`, per-category APCER, generator/device/protocol-disjoint metrics;
- API should expose `result`, `attack_type`, `physical_spoof_score`, `deepfake_score`, `protocol_consistency_score`, and `risk_reasons`.

## Pitfalls

- Do not treat deepfake detection as a replacement for active liveness. It is a digital-forgery branch that should be fused with physical PAD and protocol-consistency checks.
- Do not claim AI换脸 robustness from traditional PAD benchmarks alone.
- Do not claim external repo license/weights are usable unless actually verified.
- Do not mix active-flash data with generic static/deepfake datasets without documenting domain shift.
- Do not skip project baseline confirmation; recommendations must reference the actual deployed model/protocol family.