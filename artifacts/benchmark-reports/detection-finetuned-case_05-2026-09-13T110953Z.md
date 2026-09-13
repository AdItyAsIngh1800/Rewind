# Detection baseline — case_05

- **Generated:** 2026-09-13 11:09 UTC
- **Model:** `ml/models/yolo11n-rewind-v1/best.pt:native:conf0.25:iou0.5`
- **Device:** `mps`
- **Frames processed:** 1350

| Class | Truth | Predicted | TP | FP | FN | Precision | Recall | Note |
|---|---|---|---|---|---|---|---|---|
| `person` | 464 | 463 | 459 | 4 | 5 | 0.991 | 0.989 |  |
| `robot` | 993 | 982 | 982 | 0 | 11 | 1.000 | 0.989 |  |
| `forklift` | 0 | 0 | 0 | 0 | 0 | 1.000 | 1.000 |  |
| `pallet` | 0 | 2 | 0 | 2 | 0 | 0.000 | 1.000 |  |

## Reading this

A recall of zero against a non-zero truth count means one of two very different things, and the note column says which: the model looked and failed, or the checkpoint has no class for that entity at all. Aggregating these into one figure would hide the distinction, which is the whole reason ADR-0004 records this baseline separately.
