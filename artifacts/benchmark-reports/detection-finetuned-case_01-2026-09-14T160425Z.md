# Detection baseline — case_01

- **Generated:** 2026-09-14 16:04 UTC
- **Model:** `ml/models/yolo11n-rewind-v2/best.pt:native:conf0.25:iou0.5:edge16:nest0.9`
- **Device:** `mps`
- **Frames processed:** 1350

| Class | Truth | Predicted | TP | FP | FN | Precision | Recall | Note |
|---|---|---|---|---|---|---|---|---|
| `person` | 845 | 846 | 843 | 3 | 2 | 0.996 | 0.998 |  |
| `robot` | 1268 | 1267 | 1267 | 0 | 1 | 1.000 | 0.999 |  |
| `forklift` | 0 | 0 | 0 | 0 | 0 | 1.000 | 1.000 |  |
| `pallet` | 0 | 0 | 0 | 0 | 0 | 1.000 | 1.000 |  |

## Reading this

A recall of zero against a non-zero truth count means one of two very different things, and the note column says which: the model looked and failed, or the checkpoint has no class for that entity at all. Aggregating these into one figure would hide the distinction, which is the whole reason ADR-0004 records this baseline separately.
