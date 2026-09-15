# Detection baseline — case_04

- **Generated:** 2026-09-15 15:24 UTC
- **Model:** `ml/models/yolo11n-rewind-v3/best.pt:native:conf0.25:iou0.5:edge16:nest0.9`
- **Device:** `mps`
- **Frames processed:** 1350

| Class | Truth | Predicted | TP | FP | FN | Precision | Recall | Note |
|---|---|---|---|---|---|---|---|---|
| `person` | 0 | 0 | 0 | 0 | 0 | 1.000 | 1.000 |  |
| `robot` | 0 | 0 | 0 | 0 | 0 | 1.000 | 1.000 |  |
| `forklift` | 465 | 472 | 465 | 7 | 0 | 0.985 | 1.000 |  |
| `pallet` | 923 | 923 | 922 | 1 | 1 | 0.999 | 0.999 |  |

## Reading this

A recall of zero against a non-zero truth count means one of two very different things, and the note column says which: the model looked and failed, or the checkpoint has no class for that entity at all. Aggregating these into one figure would hide the distinction, which is the whole reason ADR-0004 records this baseline separately.
