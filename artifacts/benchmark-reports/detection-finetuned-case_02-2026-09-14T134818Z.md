# Detection baseline — case_02

- **Generated:** 2026-09-14 13:48 UTC
- **Model:** `ml/models/yolo11n-rewind-v1/best.pt:native:conf0.25:iou0.5:edge16`
- **Device:** `mps`
- **Frames processed:** 1350

| Class | Truth | Predicted | TP | FP | FN | Precision | Recall | Note |
|---|---|---|---|---|---|---|---|---|
| `person` | 321 | 24 | 21 | 3 | 300 | 0.875 | 0.065 |  |
| `robot` | 645 | 640 | 639 | 1 | 6 | 0.998 | 0.991 |  |
| `forklift` | 927 | 1321 | 908 | 413 | 19 | 0.687 | 0.980 |  |
| `pallet` | 0 | 0 | 0 | 0 | 0 | 1.000 | 1.000 |  |

## Reading this

A recall of zero against a non-zero truth count means one of two very different things, and the note column says which: the model looked and failed, or the checkpoint has no class for that entity at all. Aggregating these into one figure would hide the distinction, which is the whole reason ADR-0004 records this baseline separately.
