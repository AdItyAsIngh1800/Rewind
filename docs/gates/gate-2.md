# Gate 2 — observations become correct semantic events

- **Sub-phase:** E4.4
- **Date reviewed:** 2026-09-11 (calendar date: Week 9)
- **Verdict:** PASS, with the merge rule's limitation carried to E5

## Exit criteria

| Criterion | Measured (real pipeline, 4 tune cases) | Provisional floor | Source |
|---|---|---|---|
| Zone-event precision | 0.88 (23 TP, 3 FP) | not set at charter time | EXP-0006 |
| Zone-event recall on observable truth | 0.92 (2 FN) | not set | EXP-0006 |
| Event timing error | max 0.4 s, mean ≤ 0.1 s | ≤ 0.5 s | EXP-0006 |
| Timing error with exact positions | max 0.1 s | | EXP-0005 |
| Truth events no camera could see | 13 of 38, reported as coverage gaps | | EXP-0005 |
| Timeline endpoint | real, windowed, 404 on unknown case | | `tests/integration/test_timeline.py` |

## Contract integrity

`SCHEMA_VERSION` unchanged. `GET /cases/{id}/timeline` now returns `Timeline`
(`run_id`, window, `events`, `segments`, `identity_links`), the same shape the mock
served since PS-5 plus the run id, which the mock now returns too. `openapi.json`
regenerated and drift-checked.

## Fixture parity

Events persist and are served as `SemanticEvent`; `test_timeline` validates every
returned event against the contract. `40_events.json` still validates unchanged.

## Test coverage

| Area | Tests |
|---|---|
| Camera model, including against ray-cast truth | `tests/unit/test_camera.py` (4) |
| Extractor: crossings cite the straddling pair, first-sight and during-gap flags, occlusion pair, stop, proximity, both merge rules | `tests/unit/test_events.py` (6) |
| Events persisted by `process_run`; window query | `tests/integration/test_pipeline.py` (+1) |
| Timeline endpoint ordering, window, 404 | `tests/integration/test_timeline.py` (2) |

Total suite: 229. Nothing deferred.

## Documentation

EXP-0005 (perfect tracks), EXP-0006 (real pipeline). The camera model's measured
error envelope is in its module docstring.

## Failure cases

Catalogued in EXP-0005 and EXP-0006. The three that remain after tuning:

1. **Large vehicle from the steep camera.** Single-point localisation puts a 2.2 m
   forklift up to ~1 m along its length; CAM_C enters Z5 0.8 s early and leaves 2.5 s
   late while the other two cameras are within a frame. Owner: E5 (cross-camera
   position fusion).
2. **Partially visible entity at range.** A 38%-visible person at 16 m yields a
   fragment box whose centre lands a metre off, producing one confident wrong exit.
   Owner: E5 with a visibility-aware confidence; the detector would need to report
   partial visibility.
3. **Same-class merge.** Two people entering one zone within a second from
   different cameras would become one event. Owner: E5 identity links.

## What this phase got right by design

Bounded events. A crossing that happened during an occlusion, or a zone an entity
was already in when first seen, is emitted with the bound in its payload and half
confidence, never stamped as observed. The harness scores those separately, and the
"unobservable truth" column turns a would-be miss into a statement about camera
coverage. This is the UNKNOWN-first behaviour the charter asks for, arriving two
phases before the uncertainty engine that will render it.

## Charter alignment

No scope added. The camera model is pure maths on the existing scene config; no new
dependency. The naive merge is explicitly interim and named as such in every event
it produces (`payload.merge_rule`).

## Thresholds — proposed, awaiting sign-off with Gate 1's

| Metric | Proposed floor | Why |
|---|---|---|
| Zone-event precision, real pipeline | ≥ 0.85 | Measured 0.88 with the two known limits still present |
| Zone-event recall on observable truth | ≥ 0.90 | Measured 0.92 |
| Event timing error, max | ≤ 0.5 s | Provisional floor kept; measured 0.4 s |

## Honest verdict

Passed on four synthetic tune cases with perfect-track parity, which is the strongest
statement the design allows before E5. The 0.88 precision is three events, all with
a named cause and an owner. The golden-case exposure of 2026-09-11 (ledger) does not
touch this gate: no event threshold was chosen on those cases.
