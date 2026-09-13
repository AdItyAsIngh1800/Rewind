# Model card — `yolo11n-rewind-v1`

- **Version:** `yolo11n-rewind-v1`
- **Base checkpoint:** `yolo11n.pt`
- **Trained:** 2026-09-13 11:09:20 UTC
- **Platform:** Darwin arm64, mps
- **Weights:** `ml/models/yolo11n-rewind-v1/best.pt`

## Purpose

Detect the four REWIND entity classes — `person`, `robot`, `forklift`, `pallet` — in
frames from the three fixed warehouse cameras. It is the first stage of the
perception pipeline; its boxes feed the tracker and everything downstream.

It is a **fine-tuned** model, not one trained from scratch: pretrained initialisation,
20 epochs, 860 seconds of compute (ADR-0004).

## Data

| | |
|---|---|
| Source | `data/yolo/data.yaml`, exported by `scripts/ml/export_yolo_dataset.py` |
| Training cases | `case_01`, `case_03`, `case_04` |
| Validation case | `case_05`, the negative case |
| Held out entirely | `case_02`, `case_06` — golden, not opened until E9.1 |
| Frames | every 5th at 10 FPS, 1280x720, three cameras |
| Ground truth | ray-cast from the Blender scene, visible-box convention |

Validation uses the negative case deliberately: a model that memorised "the thing at
the intersection at 13 s" scores badly on it rather than well. Ground truth drops any
entity under 15% visible, so occlusion reads as a gap rather than a miss. Augmentation
is a training-time transform on frames and does not conflict with the scene spec's
constant-lighting rule, which fixes the rendered scene.

The training data is **entirely synthetic and entirely primitive**. Every entity is an
untextured box at its real-world footprint. No real footage, no real people.

## Training

| | |
|---|---|
| Epochs | 20 |
| Image size | 640 |
| Batch | 16 |
| Seed | 0, deterministic |
| Augmentation | HSV jitter, horizontal flip, mosaic |
| Val mAP50 | 0.995 |
| Val mAP50-95 | 0.986 |

## Metrics

Evaluated on `case_05` (1350 frames) with
`scripts/evaluation/baseline_detection.py`, scored per class against ray-cast ground
truth at IoU 0.5.

| Class | Truth | Precision | Recall | F1 | Zero-shot recall |
|---|---|---|---|---|---|
| `person` | 464 | 0.991 | 0.989 | 0.990 | 0.000 |
| `robot` | 993 | 1.000 | 0.989 | 0.994 | 0.000 |
| `forklift` | 0 | — | — | — | not present in the evaluation case |
| `pallet` | 0 | — | — | — | not present in the evaluation case |

The zero-shot column is the COCO-pretrained checkpoint with no adaptation. It is **uninformative on the current primitives** (ADR-0004, amendment of 2026-09-10): a rectangular box is not recognisable as a person, so the figure measures the geometry rather than the model. It is shown for the record, not as a baseline this model improved upon.

## Limitations

**This model has only ever seen boxes.** It was trained and evaluated on untextured
primitives in a single synthetic scene under one lighting setup. Its scores say it can
separate four box shapes and colours from a grey floor. They say nothing about real
forklifts, real people, real lighting or real cameras, and the model should be assumed
to fail on all of them until the asset swap and the public-footage check (stretch
backlog) have been done.

**Train and test share one scene.** Every camera angle, every rack position and every
floor marking in the evaluation frames was also in the training frames. This mirrors a
fixed-camera facility deployment, which genuinely is fine-tuned per site, but it means
the numbers above are a ceiling for this scene rather than an estimate for any other.

**The validation case selected the checkpoint.** `best.pt` is the epoch with the
highest validation mAP, so `case_05` is not a fully independent test. The unbiased
number arrives in E9.1 from the golden cases.

**Class balance is uneven.** `forklift` and `pallet` appear in far fewer frames than
`person` and `robot`, because only one of the three training cases contains them.
Their scores rest on less evidence.

**Unmeasured classes: `forklift`, `pallet`.** The evaluation case contains none of them, so this card makes no claim about their detection at all. The first independent number for them arrives in E9.1 from the golden cases.

## Provenance

Training record: `ml/models/yolo11n-rewind-v1/training.json`
Evaluation: `artifacts/benchmark-reports/detection-finetuned-case_05-2026-09-13T110953Z.json`
