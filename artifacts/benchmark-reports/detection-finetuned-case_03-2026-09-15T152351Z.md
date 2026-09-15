# Detection baseline — case_03

- **Generated:** 2026-09-15 15:23 UTC
- **Model:** `ml/models/yolo11n-rewind-v3/best.pt:native:conf0.25:iou0.5:edge16:nest0.9`
- **Device:** `mps`
- **Frames processed:** 1350

| Class | Truth | Predicted | TP | FP | FN | Precision | Recall | Note |
|---|---|---|---|---|---|---|---|---|
| `person` | 1539 | 1518 | 1502 | 16 | 37 | 0.989 | 0.976 |  |
| `robot` | 971 | 969 | 969 | 0 | 2 | 1.000 | 0.998 |  |
| `forklift` | 0 | 0 | 0 | 0 | 0 | 1.000 | 1.000 |  |
| `pallet` | 0 | 0 | 0 | 0 | 0 | 1.000 | 1.000 |  |

## Reading this

A recall of zero against a non-zero truth count means one of two very different things, and the note column says which: the model looked and failed, or the checkpoint has no class for that entity at all. Aggregating these into one figure would hide the distinction, which is the whole reason ADR-0004 records this baseline separately.
