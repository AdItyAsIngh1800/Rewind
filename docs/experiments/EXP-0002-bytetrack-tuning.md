# EXP-0002: ByteTrack on perfect boxes

- **Date:** 2026-09-11
- **Status:** Complete

| Field | Value |
|---|---|
| Hypothesis | Fed exact ground-truth boxes, ByteTrack recovers per-camera identities with at most 2 switches per camera per case (charter §6 floor) |
| Dataset version | `v1`, all six cases, three cameras each, 18 camera-cases |
| Preprocessing | Ground-truth observations with `track_id` stripped; `entity_id` retained for scoring only, never read by the tracker |
| Model / tracker version | Ultralytics `BYTETracker` (the `supervision` copy is deprecated and removed in 0.31) |
| Hyperparameters | Swept `match_thresh` ∈ {0.5 … 0.98}, `track_buffer` ∈ {30, 60, 100} |
| Hardware | Apple M4, CPU |
| Config version | `v0.1.0` |

## Metrics

| `match_thresh` | Total switches | Worst camera | Merged cameras |
|---|---|---|---|
| 0.50 | 58 | — | 0 |
| 0.60 | 37 | — | 1 |
| 0.70 | 21 | — | 1 |
| 0.80 (shipped default) | 13 | 4 | 1 |
| 0.85 | 7 | 2 | 1 |
| **0.90** | **6** | **2** | 1 |
| 0.95 | 5 | 2 | 1 |
| 0.98 | 5 | 2 | 1 |

`track_buffer` at 30, 60 and 100 gave identical results at every threshold.

## Failure cases

At 0.90 the six remaining switches split cleanly:

| Kind | Count | Example |
|---|---|---|
| Re-acquisition after a multi-second gap | 4 | `case_01 CAM_A P01`, 7.9 s unseen crossing the walkway |
| Re-match failure after a single missed frame | 2 | `case_03 CAM_A P02`, 0.2 s unseen |

One camera-case (`case_06 CAM_A`) merges two entities into one track at every
threshold: the pallet being carried on the forklift. The two boxes overlap almost
entirely, so to a box-only tracker they are one moving object, and physically they
are.

## Result

The intuitive tuning was wrong. Lowering `match_thresh` made every step worse. In
Ultralytics' implementation the value bounds IoU *distance*, so higher is more
permissive, the reverse of how the name reads.

`track_buffer` does nothing because it is not what loses long-gap tracks. A lost
track's Kalman prediction drifts far from where an entity reappears after seconds of
unseen motion; by the time it comes back, the predicted box has no overlap with the
real one regardless of whether the track was retained. Only appearance re-identification
bridges that, which is the cross-camera identity layer's job in E5.

## Decision

**Adopt `match_thresh = 0.90`** as the default. It meets the charter floor on every
camera-case with perfect boxes, and stops before the threshold where anything matches
anything, which would merge real detections that a noisier detector puts near one
another.

The forklift-and-pallet merge is recorded as a known limitation rather than tuned
away. Separating a load from the vehicle carrying it is a semantic distinction, not a
geometric one.

## Next experiment

`EXP-0003`: fine-tune `yolo11n` on the re-rendered (un-frozen) cases; then `EXP-0004`
runs this tracker on the fine-tuned detector's real boxes, and the difference from
these numbers is the detector's contribution to tracking error.
