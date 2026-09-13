# Gate 3 — events connect across cameras

- **Sub-phase:** E5.4
- **Date reviewed:** 2026-09-13 (calendar date: Tue 01 Dec 2026 — reached early)
- **Verdict:** PASS on the primary metric, with viewpoint-dependent appearance carried forward

## Exit criteria

| Criterion | Measured (4 tune cases) | Floor | Source |
|---|---|---|---|
| Cross-camera false-link rate, real pipeline | **0.00** (0 of 20 links) | ≤ 0.05 (charter §6) | EXP-0007 |
| Same, appearance withheld | 0.00 (0 of 19) | ≤ 0.05 | EXP-0007 |
| Same, perfect tracks | 0.00 (0 of 23) | ≤ 0.05 | EXP-0007 |
| Recall on comparable true pairs, real pipeline | 0.74 (20 of 27) | not set | EXP-0007 |
| Refusals, real pipeline | 5 UNKNOWN of 25 decisions, every one traced | — | EXP-0007 |
| Clock offset detection (E5.1) | injected 500 ms detected; `CAM_B` −0.4 s and `CAM_C` +0.2 s wrong offsets detected on real video | asserted | `test_alignment.py`, `test_pipeline.py` |
| Appearance baseline vs none (spec §D4) | +1 link net, 0 false links either way | reported | EXP-0007 |

Every number is on the tune cases, on the per-actor colour render. The golden pair is
unopened since the 2026-09-11 exposure recorded in the ledger.

## Contract integrity

`SCHEMA_VERSION` still `1.0.0`. `IdentityLink` is emitted as frozen: `decision`
LINKED or UNKNOWN, `score`, `threshold`, per-signal `components`, `evidence_refs`.
`GET /cases/{id}/timeline` serves `identity_links` in the shape the mock has served
since PS-5. The `openapi.json` drift check passes in CI.

## Fixture parity

`30_identity_links.json` validates unchanged. `process_run` persists links through
`write_links`, and `tests/integration/test_pipeline.py` asserts they arrive with
evidence refs.

## Test coverage

| Area | Tests |
|---|---|
| Clock offsets, injected 500 ms | `tests/unit/test_alignment.py` (3) |
| Appearance descriptors | `tests/unit/test_appearance.py` (4) |
| Association: co-visible, hand-over reachability, ambiguity → UNKNOWN, entity groups | `tests/unit/test_association.py` (6) |
| Events merged by identity group | `tests/unit/test_events.py` (7) |
| Links persisted by `process_run`; wrong offsets detected | `tests/integration/test_pipeline.py` |
| Edge-sliver rule | `tests/unit/test_detector_edge.py` (4) |
| Alignment guard under occlusion and at the frame edge | `tests/unit/test_verify_alignment.py` (5) |

Total suite: 253. Nothing deferred.

## Documentation

EXP-0007. Re-runs appended to EXP-0003, EXP-0004 and EXP-0006 after the colour fix.
Ledger rows for the colour fix (`BUG-FIX`), the history scrub, and the E8.2 deferral.

## Failure cases

All five are in EXP-0007 with their signals. Grouped by cause:

1. **Viewpoint changes an entity's colour distribution.** The pallet seen from the
   steep CAM_C (appearance 0.02) and a person seen from two angles (0.40) are
   refused despite good geometry. Recall cost, not a false link.
2. **Edge-cut entity.** P02 at the bottom of CAM_B has neither a usable position nor
   a usable crop; refused in every mode, correctly.
3. **Fragmented track.** P01's long-gap re-acquisition leaves two CAM_A segments
   close enough in score that the ambiguity rule refuses one hand-over.

## Bugs this phase found in earlier phases

| Bug | Phase | Found by |
|---|---|---|
| Configured camera clock offsets never baked into the clips; ingestion had shifted two cameras since E2 | E1.2 / E2 | E5.1 clock check on its first run |
| Every actor rendered in its class colour; P01 and P02 indistinguishable | E1.2 | E5.2 descriptors had nothing to separate |
| Alignment guard ignored occlusion | E1.2 guard | The per-actor re-render |
| Retrained detector emitted edge slivers that split tracks | E3.1 | The Gate 3 re-measurement |

## Charter alignment

No scope added. Appearance is a colour histogram of the centre of the box: no face,
no biometric, in line with the §4 non-goal. The embedding comparison spec §D4 invites
was not built; EXP-0007 records why it is not needed yet.

## Thresholds — proposed, awaiting sign-off

| Metric | Proposed floor | Why |
|---|---|---|
| Cross-camera false-link rate | ≤ 0.05 (keep) | The thesis metric. Measured 0; not a calibration to tighten on four cases |
| Recall, real pipeline | ≥ 0.65 | Measured 0.74. Tolerates losing two of 27 pairs, which is the per-case swing appearance alone produces |

## Honest verdict

Passed on the metric that matters, and the refusals are the right refusals. But the
zero was earned on four cases with at most three entities and no look-alike close in
space and time: the `case_03` decoy was separated by geometry before appearance was
consulted. This gate shows the linker is conservative; it does not yet show it under
pressure. That is measured at E9.1 on the golden pair. The roadmap's instruction for
this phase — ship conservative, do not extend — applies, and nothing here asks for
more E5 time.

## Carry-forwards

1. Viewpoint-dependent appearance → optional embedding experiment, triggered only if
   E7 needs a link the histogram refuses.
2. Identity-keyed event merge has no same-class collision in the tune cases to prove
   it → E9.1.
3. Edge-cut and fragment-box positions are biased → E7.3, as low-confidence
   localisation in the uncertainty engine.
