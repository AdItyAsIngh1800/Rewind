# Detection baseline — case_03

- **Generated:** 2026-09-14 15:38 UTC
- **Model:** `ml/models/yolo11n-rewind-v1/best.pt:native:conf0.25:iou0.5:edge16:nest0.9`
- **Device:** `mps`
- **Frames processed:** 1350

| Class | Truth | Predicted | TP | FP | FN | Precision | Recall | Note |
|---|---|---|---|---|---|---|---|---|
| `person` | 1539 | 1515 | 1506 | 9 | 33 | 0.994 | 0.979 |  |
| `robot` | 971 | 968 | 968 | 0 | 3 | 1.000 | 0.997 |  |
| `forklift` | 0 | 0 | 0 | 0 | 0 | 1.000 | 1.000 |  |
| `pallet` | 0 | 1 | 0 | 1 | 0 | 0.000 | 1.000 |  |

## Reading this

A recall of zero against a non-zero truth count means one of two very different things, and the note column says which: the model looked and failed, or the checkpoint has no class for that entity at all. Aggregating these into one figure would hide the distinction, which is the whole reason ADR-0004 records this baseline separately.
