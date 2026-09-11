# EXP-0005: Semantic events from perfect tracks

- **Date:** 2026-09-11
- **Status:** Complete

| Field | Value |
|---|---|
| Hypothesis | Given exact tracks, the event extractor recovers every zone crossing a camera could have seen, within 0.5 s; localising from boxes instead of truth positions costs precision only where the single-point model is known to be biased |
| Dataset version | `v1`, the four tune cases; golden pair sealed (see the ledger row for the breach on this date) |
| Preprocessing | Ground-truth observations with `track_id := entity_id`. Run A keeps `world_xyz`; run B strips it so positions come from `CameraModel.back_project` at half class height |
| Model / tracker version | `events:stop0.1/1.0:turn60.0/0.5:prox1.5:occ0.5`, merge rule "type+zone+class within 0.5 s" (widened to 1.0 s and stamped at the median camera time in EXP-0006; the truth-position rows below are unchanged by that, the projected rows improve by one event) |
| Hyperparameters | Swept `turn_min_speed` ∈ {0.2…0.8} (no effect) and `turn_baseline_s` ∈ {frame, 0.5, 1.0} |
| Hardware | Apple M4, CPU |
| Config version | `v0.1.0` |

## Metrics

Zone entry/exit only; other event types have no ground-truth timeline yet. Truth
events are **observable** when some camera saw the entity within 0.5 s of them; the
rest are coverage gaps and are counted, not scored. Predictions that admit their time
is a bound (first sight inside a zone, crossing during an occlusion) can match truth
but are not false positives when they do not.

| Case | Positions | TP | FP | FN | P | R | Max timing | Unobservable truth | Bounded predictions |
|---|---|---|---|---|---|---|---|---|---|
| case_01 | truth | 7 | 0 | 0 | 1.00 | 1.00 | 0.1 s | 1 | 3 |
| case_03 | truth | 7 | 0 | 0 | 1.00 | 1.00 | 0.1 s | 0 | 1 |
| case_04 | truth | 8 | 0 | 0 | 1.00 | 1.00 | 0.1 s | 9 | 2 |
| case_05 | truth | 3 | 0 | 0 | 1.00 | 1.00 | 0.1 s | 3 | 1 |
| case_01 | projected | 7 | 1 | 0 | 0.88 | 1.00 | 0.2 s | 1 | 2 |
| case_03 | projected | 7 | 1 | 0 | 0.88 | 1.00 | 0.4 s | 0 | 1 |
| case_04 | projected | 6 | 2 | 2 | 0.75 | 0.75 | 0.1 s | 9 | 2 |
| case_05 | projected | 3 | 0 | 0 | 1.00 | 1.00 | 0.1 s | 3 | 1 |

Telemetry-only truth (`state_change` from the robot's scripted e-stop) is 2 events in
case_01 and case_03 and is not recoverable from video by construction.

## Failure cases

| Case | What | Cause |
|---|---|---|
| case_04, projected, CAM_C | Forklift enters Z5 at 4.5 s (truth 5.3) and leaves at 31.2 s (truth 28.7) | A 2.2 m vehicle's box centre back-projected at half height lands up to ~1 m along its length from the steep overhead camera. CAM_A and CAM_B time the same crossings within 0.1 s. Single-point-per-box limit, documented in `packages/common/camera.py`; E5 averages positions across cameras |
| case_04 | 9 truth events unobservable | The pallet rides hidden on the forklift until 14.1 s and the loading bay (Z4) has no coverage. Both are the scene, not the extractor |
| case_01 | P01's Z3 exit at 7.2 s | Inside the 2.9–9.6 s occlusion. Emitted as a bounded exit at 10.6 s with `during_gap: [2.9, 10.6]`, exactly the "cannot determine" interval E7.3 will render |
| all, projected, before tuning | 18–73 direction changes per case against 1–5 | Frame-to-frame heading on jittering positions. Fixed by measuring heading over a 0.5 s baseline: projected counts 4/6/4/3 against truth 3/3/3/3 |

## Result

With exact positions the extractor is lossless on the tune cases and its timing error
is one frame. Localisation from boxes keeps recall except for the forklift-from-above
case and adds one spurious crossing per case from boundary jitter. The
bounded/unobservable split is the important output: on these four cases, 13 truth
events could not have been seen by any camera, and the harness now says so instead
of scoring them as misses.

## Decision

**Adopt** the extractor, the config above, and the naive cross-camera merge as the E4
baseline. Turn baseline 0.5 s is the only threshold moved from its geometry default.
Zone hysteresis was considered for the boundary jitter and rejected for now: it would
also delay every real crossing, and the projected false positives are one per case.

## Next experiment

E4.3 persists this stream and serves the timeline. `EXP-0006`, in E4.4 after real
tracks replace perfect ones: the same table on `tracking_on_detections` output.
