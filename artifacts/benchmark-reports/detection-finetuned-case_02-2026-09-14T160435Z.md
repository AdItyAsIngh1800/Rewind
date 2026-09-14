# Detection baseline — case_02

- **Generated:** 2026-09-14 16:04 UTC
- **Model:** `ml/models/yolo11n-rewind-v2/best.pt:native:conf0.25:iou0.5:edge16:nest0.9`
- **Device:** `mps`
- **Frames processed:** 1350

| Class | Truth | Predicted | TP | FP | FN | Precision | Recall | Note |
|---|---|---|---|---|---|---|---|---|
| `person` | 321 | 70 | 18 | 52 | 303 | 0.257 | 0.056 |  |
| `robot` | 645 | 643 | 643 | 0 | 2 | 1.000 | 0.997 |  |
| `forklift` | 927 | 432 | 432 | 0 | 495 | 1.000 | 0.466 |  |
| `pallet` | 0 | 0 | 0 | 0 | 0 | 1.000 | 1.000 |  |

## Reading this

A recall of zero against a non-zero truth count means one of two very different things, and the note column says which: the model looked and failed, or the checkpoint has no class for that entity at all. Aggregating these into one figure would hide the distinction, which is the whole reason ADR-0004 records this baseline separately.
