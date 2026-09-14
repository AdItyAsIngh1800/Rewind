# Detection baseline — case_02

- **Generated:** 2026-09-14 13:48 UTC
- **Model:** `yolo11n.pt:coco:conf0.25:iou0.5:edge16`
- **Device:** `mps`
- **Frames processed:** 1350

| Class | Truth | Predicted | TP | FP | FN | Precision | Recall | Note |
|---|---|---|---|---|---|---|---|---|
| `person` | 321 | 0 | 0 | 0 | 321 | 1.000 | 0.000 |  |
| `robot` | 645 | 0 | 0 | 0 | 645 | 1.000 | 0.000 | no COCO class exists for this entity |
| `forklift` | 927 | 0 | 0 | 0 | 927 | 1.000 | 0.000 | reached only via the COCO `truck` class, a poor stand-in |
| `pallet` | 0 | 0 | 0 | 0 | 0 | 1.000 | 1.000 | no COCO class exists for this entity |

## Reading this

A recall of zero against a non-zero truth count means one of two very different things, and the note column says which: the model looked and failed, or the checkpoint has no class for that entity at all. Aggregating these into one figure would hide the distinction, which is the whole reason ADR-0004 records this baseline separately.
