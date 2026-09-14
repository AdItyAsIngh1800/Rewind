# Gate 7 — benchmark results and failure modes are measurable

- **Sub-phase:** E9.1, with the post-golden pass (EXP-0011)
- **Date reviewed:** 2026-09-14 (calendar date: Tue 12 Jan 2027 — reached early)
- **Verdict:** **PASS on the gate's own criterion**: every charter floor is measured on
  the held-out pair, every failure is traced to a cause, and every fix is measured beside
  the held-out number. **The system does not meet the charter floors on unseen cases**
  with real detections; it meets the reasoning-layer behaviours with perfect tracks.
  Recorded, not excused.

## Exit criteria

| Criterion | Evidence |
|---|---|
| Held-out cases opened once, under a pre-registered protocol | EXP-0010, committed `03a0732` before the run; log `artifacts/golden-run-2026-09-14.log` |
| Every charter §6 floor measured on them | `artifacts/benchmark-reports/final.md`: 15 rows, 7 PASS, 8 FAIL |
| Every failure traced to a cause | EXP-0010 "Failure analysis": F1–F7, each with the frame, track or code path behind it |
| Baseline against every learned component | Detector: COCO `yolo11n.pt` (0 detections) against `yolo11n-rewind-v1`; identity: geometry-and-time only against colour descriptors (final.md) |
| Fixes measured without replacing the held-out number | EXP-0011: six fixes in the owner's order, each on all six cases; thresholds from tune cases or pipeline properties; post-golden columns added beside held-out in final.md |

## What passes and what fails, after the fixes

Charter floors on the golden pair, real detections: **PASS** robot detection, ID
switches (now 1), timing, evidence coverage, unsupported-claim rate, gap recall.
**FAIL** person detection (F2, accepted), zone events (0.58 / 0.37), false-link rate
(0.29, F4 partial), cross-camera recall (0.29), cause top-3 and top-1 (3 of 5, 0.60).

Golden behaviours with perfect tracks: all five that failed on reasoning now pass (C02's
person worded *Possible* from a gap; the gap written as *Cannot determine*; no false
*Observed* claim; C06's two forklifts both ranked, F02 second). With real detections,
C02.4 and C02.5 pass; C02.3, C06.2 and C06.3 fail because the entity is not detected
(F1, F2).

The line between them is the point: every floor that fails is a perception floor, and
the layers above perception do what the charter asks of them on inputs they were never
tuned on.

## Contract integrity

`SCHEMA_VERSION` `1.1.0` (ADR-0006, additive: runs record their media and capture time).
No contract changed during E9.1 or EXP-0011. `openapi.json` drift check green.

## Fixture parity

Golden fixtures validate unchanged. Real output from the golden pair parses under every
frozen contract; the harnesses would have raised otherwise.

## Test coverage

301 passed against an ephemeral Postgres (33 of them skip without one). Each fix in
EXP-0011 left a unit test: confirmed transitions (3), before-trigger gap claims (1),
bounded-event candidates (3), first rest and contact candidates (1 + 3), nested boxes
(`test_detector_edge.py`). E9.4's failure tests (worker restart, corrupt video, Redis
down, one camera missing) and the Playwright e2e are still owed.

## Documentation

EXP-0010 (pre-registration, results, failure analysis), EXP-0011 (fixes, verdict),
final.md, ledger rows for F1 (v2 not promoted) and F2 (accepted), charter §6 accepted
limitations. Model card for `yolo11n-rewind-v1` still owed (E9.2); v2 is not promoted and
gets none.

## Charter alignment

Nothing was added outside §4. The one temptation, a second training run with a hue
jitter chosen to recover case_02, was declined as tuning on a golden case.

## Honest verdict

Gate 7 asks whether results and failure modes are *measurable*. They are, to the frame.
It does not ask whether the numbers are good, and on real detections half of them are
not. Two of the eight failing floors are accepted limitations with a documented design
answer (F2's *Cannot determine*, F1's re-render). The rest are consequences of those two
through the pipeline: a forklift never detected cannot be linked or ranked. The gate is
passed on its criterion, and the charter floors on unseen data are recorded as failed on
perception and met on reasoning.

## Owed after this gate

- E1 re-render with a second forklift colour or a truncated forklift view in a tune case;
  retrain; measure (F1's next attempt).
- Model card for `yolo11n-rewind-v1` with its limitations (E9.2).
- Failure catalogue with frame screenshots (E9.2), from EXP-0010's traces.
- Mentor walkthrough of C01 (ledger DEBT since E9.1).
- E9.3 profiling; E9.4 failure tests and Playwright.
