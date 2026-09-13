# Gates 4 and 5 — reconstructed without an LLM, and every conclusion traceable

- **Sub-phase:** E7.5
- **Date reviewed:** 2026-09-13 (calendar date: Tue 22 Dec 2026 — reached early)
- **Verdict:** Gate 5 **PASS**. Gate 4 **PASS** on cause ranking; calibration question
  decided (option A) and thresholds signed off 2026-09-13; golden-case behaviours still
  unmeasured

## Exit criteria

| Criterion | Measured (3 tune incidents × 2 modes) | Floor | Source |
|---|---|---|---|
| Incident reconstructed without an LLM | Graph, hypotheses and report generated for every incident by `process_run`; generator is template-only | — | `deterministic-0.1.0` |
| Annotated cause ranked first | **6 of 6** | not set | EXP-0009 |
| Annotated cause in top 3 | 6 of 6 | not set | EXP-0009 |
| **Evidence coverage** | **1.00** in every report | ≥ 0.95 (charter §6) | EXP-0009 |
| **Unsupported-claim rate** | **0.00** in every report | 0.00 (charter §6) | EXP-0009 |
| Unseen intervals named (gap recall) | 1.00 wherever truth has a gap | not set | EXP-0009 |
| Named gaps that were truly unseen (gap precision) | 0.95–1.00, except 0.00 on case_03 detections (identity fragmentation) | not set | EXP-0009 |
| Report language bound to evidence level | Enforced by the `Claim` contract; a mismatched phrase cannot be constructed | structural | `packages/schemas/evidence.py` |
| A citation to missing evidence stops the report | Generator raises `ReportError` | structural | `test_a_citation_to_missing_evidence_stops_the_report` |

Gate 5 is structural, not statistical: an uncited claim cannot be built, and a dangling
citation cannot be issued. The measured 0.00 confirms the mechanism on real output; it
does not depend on it.

## Contract integrity

`SCHEMA_VERSION` still `1.0.0`. `EvidenceNode`, `EvidenceEdge`, `Hypothesis`, `Claim` and
`Report` are emitted as frozen in PS-4, including the validators. `GET /cases/{id}/evidence`
serves the mock's `{nodes, edges}` shape and `GET /cases/{id}/report` its
`{report, hypotheses}` shape, now real. `openapi.json` regenerated; drift check green.

## Fixture parity

`60_evidence_graph.json`, `70_hypotheses.json` and `80_report.json` validate unchanged.
Real output uses the same node types, relations and evidence levels as the fixtures.
Observations are not graph nodes, a scope choice recorded in the ledger.

## Test coverage

| Area | Tests |
|---|---|
| Coverage gaps across cameras and window edges; identity conflicts; telemetry join | `tests/unit/test_evidence_graph.py` (8) |
| Ranking: flagship first, gap caps at POSSIBLE, UNKNOWN when nothing fits, blocked zone, edge ids | `tests/unit/test_hypotheses.py` (5) |
| Report: coverage and unsupported rate by the benchmark metrics, claim order and wording, missing citation raises | `tests/unit/test_report.py` (4) |
| Graph, hypotheses and report stored by `process_run` on real video | `tests/integration/test_pipeline.py` |
| Evidence and report endpoints, 404s | `tests/integration/test_cases.py` |

Total suite: 283. Nothing deferred.

## Documentation

ADR-0005 (graph in Postgres). EXP-0008 (incident triggers), EXP-0009 (reconstruction).
Ledger rows for observations not being nodes, the telemetry source, and clip references.

## Failure cases

All traced in EXP-0009:

1. **Flagship cause worded "Conflicting evidence" on real detections** (case_01, case_03):
   a refused cross-camera comparison between two tracks that other links joined into
   one person covers the approach.
2. **False gap on an unlinked fragment** (case_03, P02): a refusal splits one person into
   two entities, each "unseen" while the other is seen.
3. **Pallet fragment as a second, low-ranked candidate** (case_04).

## Bugs this phase found in earlier phases

| Bug | Phase | Found by |
|---|---|---|
| Identity conflicts spanned both segments whole, so any refusal touching an actor would have capped every hypothesis about it | E7.3 (same phase) | Tracing the first ranker test |
| Conflict nodes labelled by group, reading "X and X" for a refusal inside a group | E7.1 (same phase) | EXP-0009 failure trace |

## Charter alignment

No scope added. No LLM anywhere on the path; the stretch LLM layer would sit behind
`services/reporting`, never in front. No face or biometric signal is used in any
hypothesis.

## Decision — how a refusal inside a group affects a hypothesis

On real detections the identity layer sometimes links A↔B and B↔C but refuses A↔C
directly. The group still says one person. Today that refusal counts against any
hypothesis about the person whose critical interval it overlaps, capping it at
*Conflicting evidence*.

| Option | Effect on the tune cases | Trade-off |
|---|---|---|
| **A. Keep as is** *(recommended until E9.1)* | case_01 and case_03 detections stay *Conflicting evidence* | Never over-claims; the C01 demo reads weaker than the evidence mostly supports |
| B. Count an in-group refusal against a hypothesis only if its score is below the link threshold | case_01 becomes *Likely contributed* (0.79 ≥ 0.75); case_03 stays conflicting (0.738) | Distinguishes "refused for ambiguity" from "refused as unlike"; a rule chosen after seeing two cases |
| C. Count a refusal only if one of its two tracks supports the anchor event | Needs the ranker to know which tracks back each event; outcome not yet measured | Most precise, most code, and still fitted on two cases |

Recommendation: **A now, revisit with the golden cases in E9.1**, where C02 and C06
give the first evidence not used to design the rule.

**Decided 2026-09-13 by the owner: A.** Two reasons, recorded so E9.1 does not reopen
this without new evidence:

1. *Procedural.* B and C would be a threshold or matching rule picked after reading
   case_01 and case_03, and case_01 is the case the rule would fix. That is the scoring
   logic fitted to the demo, the thing the sealed golden pair exists to prevent.
2. *Directional.* Wording the flagship cause *Conflicting evidence* when the truth is
   *Likely contributed* says less than the truth. That is the failure the charter
   prefers, the same shape as the 0.00 unsupported-claim floor: an honest
   understatement is cheap, an overstatement is what E7 exists to prevent.

Revisit only if the golden cases show the rule costing a correct conclusion, not only
wording.

## Thresholds — signed off 2026-09-13

| Metric | Proposed floor | Why |
|---|---|---|
| Evidence coverage | ≥ 0.95 (keep charter) | Measured 1.00; the contract makes lower structurally unlikely, the floor catches a regression in how claims are built |
| Unsupported-claim rate | 0.00 (keep charter) | Structural |
| Cause top-3 | 1.00 on tune incidents | Measured 1.00; three incidents cannot support a fractional floor |
| Cause top-1 | ≥ 0.67 | Measured 1.00; tolerates one of three, since ranking under ambiguity (C06) is expected to be close |
| Gap recall | ≥ 0.90 | Measured 1.00 |

## Still owed before this gate is fully closed

- **End-to-end walkthrough with the mentor** (roadmap E7.5). A person, not a test, has to
  read a C01 report against its replay.
- **The golden behaviours** (C02 UNKNOWN, C06 two causes), at E9.1.

## Honest verdict

Gate 5 is passed in the strongest sense the design allows: the generator cannot issue
an uncited or mis-cited claim, and on real output it never tried to. Gate 4 is passed
on the tune cases for **which** cause, in both modes. It is not yet passed for the case
the project is named around, an incident whose decisive moment nobody saw, because
that case is golden and unopened. The one real weakness, conflicting wording on
flagship detections, errs toward saying less, and is put to the owner rather than
tuned away.
