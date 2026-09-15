# Model card — `yolo11n-rewind-v3`

- **Version:** `yolo11n-rewind-v3`
- **Base checkpoint:** `yolo11n.pt`
- **Trained:** 2026-09-15 15:23:18 UTC
- **Platform:** Darwin arm64, mps
- **Weights:** `ml/models/yolo11n-rewind-v3/best.pt`

## Purpose

Detect the four REWIND entity classes — `person`, `robot`, `forklift`, `pallet` — in
frames from the three fixed warehouse cameras. It is the first stage of the
perception pipeline; its boxes feed the tracker and everything downstream.

It is a **fine-tuned** model, not one trained from scratch: pretrained initialisation,
20 epochs, 2091 seconds of compute (ADR-0004).

## Data

| | |
|---|---|
| Source | `data/yolo/data.yaml`, exported by `scripts/ml/export_yolo_dataset.py` |
| Training cases | `case_01`, `case_03`, `case_04`, `case_07` |
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
| Val mAP50-95 | 0.983 |

## Metrics

Evaluated on `case_05` (1350 frames) with
`scripts/evaluation/baseline_detection.py`, scored per class against ray-cast ground
truth at IoU 0.5.

| Class | Truth | Precision | Recall | F1 | Zero-shot recall |
|---|---|---|---|---|---|
| `person` | 464 | 0.994 | 0.994 | 0.994 |  |
| `robot` | 993 | 0.999 | 0.990 | 0.994 |  |
| `forklift` | 0 | — | — | — | not present in the evaluation case |
| `pallet` | 0 | — | — | — | not present in the evaluation case |

## Golden cases, post-golden (EXP-0013)

`case_02` and `case_06` were opened in EXP-0010 before this checkpoint's data existed, so these are not held-out numbers. They are measured beside the held-out ones in `artifacts/benchmark-reports/final.md`, never in their place.

`case_02` (1350 frames):

| Class | Truth | Precision | Recall | F1 |
|---|---|---|---|---|
| `person` | 321 | 0.870 | 0.062 | 0.116 |
| `robot` | 645 | 0.998 | 0.992 | 0.995 |
| `forklift` | 927 | 0.999 | 0.996 | 0.997 |
| `pallet` | 0 | — | — | — |

`case_06` (1350 frames):

| Class | Truth | Precision | Recall | F1 |
|---|---|---|---|---|
| `person` | 0 | — | — | — |
| `robot` | 0 | — | — | — |
| `forklift` | 994 | 0.956 | 0.930 | 0.942 |
| `pallet` | 1045 | 0.984 | 0.981 | 0.982 |

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
number is the held-out section.

**Class balance is uneven.** `forklift` and `pallet` appear in far fewer frames than
`person` and `robot`, because only one of the three training cases contains them.
Their scores rest on less evidence.

**Unmeasured classes: `forklift`, `pallet`.** The evaluation case contains none of them, so this card makes no claim about their detection at all. Their only independent numbers are in the held-out section.

**Found on the golden cases, post-golden (EXP-0013).** Trained after EXP-0010 on the
three tune cases plus `case_07`, which shows a navy forklift cut by a frame edge; the
golden numbers below neither trained nor selected the model, but the case that did
was designed from the failure catalogue's description of them.

**A person at a fifth of their silhouette is still not detected.** `case_02`'s P01 behind
the parked forklift: 20 of 321 boxes (F2, accepted limitation). Person recall 0.062
against 0.065 for v1, with F02 now found: the postmortem's test that F2 is a visibility
limit and not a training gap, passed.

**Two forklifts can share one track on one camera.** On `case_06`'s CAM_A, F01 leaves the
view at 12.2 s and F02 enters nearby at 12.6 s, inside ByteTrack's 3 s buffer; the
tracker continues F01's id onto F02. The ID-switch metric counts an entity changing
track, not a track changing entity, so this is invisible to it (F8). A cross-camera
consumer of that track sees one forklift where there were two.

**A pallet being pushed splits and flips its track.** On the same camera, PL3 alternates
between two tracks four times in 1.3 s (20.9–22.2 s) while F02 pushes it into the
zone: four switches against a floor of two (F9). v1 never showed this because it never
detected the forklift doing the pushing. A tracker setting, not a detector one; it is
the cost of seeing F02.

**A forklift half outside the frame can produce a second box on its front face** (F4).
The nested-box rule (`nest0.9`) drops one inside a larger box; on `case_02` v3's boxes
are clean enough that no fragment track is linked across cameras, and the false-link
count there is 0 of the pairs compared.

## Provenance

Training record: `ml/models/yolo11n-rewind-v3/training.json`
Evaluation: `artifacts/benchmark-reports/detection-finetuned-case_05-2026-09-15T152411Z.json`
Held-out: `artifacts/benchmark-reports/detection-finetuned-case_02-2026-09-15T152340Z.json`, `artifacts/benchmark-reports/detection-finetuned-case_06-2026-09-15T152422Z.json`
