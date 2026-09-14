# Detection baseline — case_06

- **Generated:** 2026-09-14 15:39 UTC
- **Model:** `ml/models/yolo11n-rewind-v1/best.pt:native:conf0.25:iou0.5:edge16:nest0.9`
- **Device:** `mps`
- **Frames processed:** 1350

| Class | Truth | Predicted | TP | FP | FN | Precision | Recall | Note |
|---|---|---|---|---|---|---|---|---|
| `person` | 0 | 0 | 0 | 0 | 0 | 1.000 | 1.000 |  |
| `robot` | 0 | 0 | 0 | 0 | 0 | 1.000 | 1.000 |  |
| `forklift` | 994 | 283 | 257 | 26 | 737 | 0.908 | 0.259 |  |
| `pallet` | 1045 | 1023 | 1015 | 8 | 30 | 0.992 | 0.971 |  |

## Reading this

A recall of zero against a non-zero truth count means one of two very different things, and the note column says which: the model looked and failed, or the checkpoint has no class for that entity at all. Aggregating these into one figure would hide the distinction, which is the whole reason ADR-0004 records this baseline separately.
