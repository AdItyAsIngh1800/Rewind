# EXP-0001: COCO zero-shot detection on primitives

- **Date:** 2026-09-11
- **Status:** Complete

| Field | Value |
|---|---|
| Hypothesis | A COCO-pretrained `yolo11n` will detect `person` in the rendered scene and reach `forklift` via `truck`; `robot` and `pallet` will be missed for lack of a class |
| Dataset version | `v1` (`case_01`, 1,350 frames across three cameras) |
| Preprocessing | Deterministic 1:1 sampling at 10 FPS, no resize beyond the model's own letterboxing |
| Model / tracker version | `yolo11n.pt:coco:conf0.25`, no tracker |
| Hyperparameters | confidence 0.25, IoU 0.7, float32 |
| Hardware | Apple M4, MPS |
| Config version | `v0.1.0` |

## Metrics

| Class | Truth | Predicted | Recall | Note |
|---|---|---|---|---|
| `person` | 845 | 0 | 0.000 | COCO has this class |
| `robot` | 1,268 | 0 | 0.000 | no COCO class |
| `forklift` | 0 | 0 | — | not present in `case_01` |
| `pallet` | 0 | 0 | — | not present in `case_01` |

## Failure cases

Every frame. The model returned **no detections of any class** over 1,350 frames.

## Result

The hypothesis was wrong in an instructive way. `person` scored zero despite COCO
covering the class, so the missing-class explanation cannot be the cause.

Diagnosed by running the identical checkpoint on the photorealistic P3 reference
image of the same four entities: it returned `person`, `truck` and `car`. The model
works. The entities in the scene are untextured rectangular primitives, and a grey box
is not a person to a network trained on photographs.

## Decision

Recorded as the zero-shot figure, **annotated as uninformative on primitives** rather
than presented as a baseline (`ADR-0004`, amendment of 2026-09-10). Fine-tuning
proceeds on the primitives and is measured as detection ability per class, not as
improvement over this figure. The comparison becomes meaningful for free once real
assets replace the primitives, since only the input images change.

## Next experiment

`EXP-0002`: fine-tune `yolo11n` on the four tuning cases with native entity classes,
validate on `case_05`, and report per-class precision, recall and F1. Golden cases
`case_02` and `case_06` are not opened.
