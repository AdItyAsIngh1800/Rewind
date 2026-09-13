# EXP-0003: Fine-tune yolo11n on the corrected render

- **Date:** 2026-09-11
- **Status:** Complete

| Field | Value |
|---|---|
| Hypothesis | Twenty epochs of fine-tuning from the COCO checkpoint recovers all four entity classes on the primitive scene, where zero-shot recovers none (ADR-0004) |
| Dataset version | `v1`, re-rendered after the frozen-actor fix; `verify-alignment` green on all 18 clips |
| Preprocessing | `export_yolo_dataset.py`: every 5th frame, 1280x720 → 640; train `case_01/03/04` (810 frames), val `case_05` (270); golden `case_02/06` sealed |
| Model / tracker version | `yolo11n.pt` → `yolo11n-rewind-v1` |
| Hyperparameters | epochs 20, imgsz 640, batch 16, seed 0, Ultralytics default augmentation (HSV, flip, mosaic) |
| Hardware | Apple M4 16 GB, MPS, 827 s |
| Config version | `v0.1.0` |

## Metrics

Per class at IoU 0.5, confidence 0.25, NMS 0.5 (`baseline_detection.py`).

| Class | Case | Truth | Precision | Recall | Zero-shot recall (EXP-0001) |
|---|---|---|---|---|---|
| `person` | case_05 (val) | 464 | 0.987 | 0.994 | 0.000 |
| `robot` | case_05 (val) | 993 | 0.997 | 0.992 | no COCO class |
| `forklift` | case_04 (**train**) | 465 | 0.985 | 1.000 | 0.000 via `truck` |
| `pallet` | case_04 (**train**) | 923 | 1.000 | 0.999 | no COCO class |

Val mAP50 0.995, mAP50-95 0.987 (`ml/models/yolo11n-rewind-v1/training.json`).

The forklift and pallet rows are a training-set sanity check, not an evaluation:
`case_05` contains neither class and `case_04` is the only tune case that does. Their
first independent number arrives from the golden cases in E9.1. The model card marks
them unmeasured.

## Failure cases

| Frames | What | Cause |
|---|---|---|
| `case_03 CAM_A` 37–449 | Two boxes for one person, IoU ~0.65 between them | P01 stands in front of P02 for 22 s; the detector emits both the visible part and the full amodal extent, and NMS at 0.7 keeps both. Fixed by NMS 0.5 (see EXP-0004). |
| `case_05` | 6 false positive persons, 8 missed robots out of 993 | Not inspected individually; within the 1% noise floor of a 20-epoch run and below the level any downstream stage is sensitive to. |

## Result

The frozen-actor bug, not the model, was the 0.083 mAP of the first attempt: the same
recipe on the corrected render reaches 0.987. Zero-shot remains 0 on every class for
the structural reason ADR-0004 records, so the comparison is between "cannot" and
"can", not between two competent models.

## Decision

**Adopt `yolo11n-rewind-v1`** as the worker's detector. It is the checkpoint
`apps/worker/settings.py` points at by default.

## Next experiment

`EXP-0004`: the tracker fed by this detector rather than by perfect boxes.

## Re-run, 2026-09-13 — per-actor colour render

The render gave every actor its class colour; scene spec §5 asks for one vest colour
per actor. P02 is now orange and F02 navy (`scene_v1.json` `actor_colours`), the 18
clips were re-rendered, `verify-alignment` and `validate-gt` pass, and the same recipe
was trained again over the old checkpoint (860 s). Ledger row `BUG-FIX`.

| Class | Case | Precision (was) | Recall (was) |
|---|---|---|---|
| `person` | case_05 (val) | 0.991 (0.987) | 0.989 (0.994) |
| `robot` | case_05 (val) | 1.000 (0.997) | 0.989 (0.992) |
| `forklift` | case_04 (train) | 0.998 (0.985) | 0.998 (1.000) |
| `pallet` | case_04 (train) | 1.000 (1.000) | 0.999 (0.999) |

Val mAP50 0.995, mAP50-95 0.986 (was 0.987). Zero-shot on `case_01`: still 0
detections. Every movement is within a few boxes of a 1,000-box case, i.e. inside the
run-to-run noise of a 20-epoch fine-tune. The same rows are identical with the edge
rule added in the EXP-0004 re-run. **Decision stands.**
