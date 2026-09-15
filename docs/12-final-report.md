# REWIND — final report

**Evidence-backed incident reconstruction for multi-camera video, without a language
model in the path.**

Aditya Singh · September 2026 · repository `AdItyAsIngh1800/Rewind`

## Abstract

REWIND takes three fixed-camera recordings of a simulated warehouse, detects and
tracks people, robots, forklifts and pallets, converts trajectories to semantic
events, opens an incident when a robot emergency-stops or a zone stays blocked, rewinds
the footage across cameras into an investigation window, builds an evidence graph
with provenance on every node and edge, ranks candidate causes with both supporting
and contradicting references, and writes a report whose vocabulary is bound to an
evidence level and whose every material claim cites stored evidence. Intervals no
camera saw are first-class: they are nodes in the graph, hatched intervals in the
investigator's timeline, and *Cannot determine* claims in the report.

On two held-out cases opened once under a pre-registered protocol, every report
achieved evidence coverage 1.00 and an unsupported-claim rate of 0.00, gap recall was
at least 0.995, and the reasoning layer produced the required behaviours on perfect
tracks. The perception layer did not generalise to an appearance absent from its
three tune cases: person recall 0.065 and one forklift never detected. Eight of the
charter's fifteen floors failed on unseen data, every failure is traced to a frame,
and every fix is measured beside the held-out number rather than in its place.

The contribution is not a model. It is a system in which the honesty of the output is
structural — enforced by contracts, not by prompt — and an engineering record that
shows what that costs.

## 1. Problem

Multi-camera video systems show footage. After an incident, the question is not
"what was recorded" but "what happened, what caused it, and what cannot be known from
the recording". Existing investigator tools answer the first; language models asked to
answer the second produce fluent reconstructions in which an inferred cause and an
observed fact are indistinguishable, and an interval no camera saw is quietly filled.

The specification (`REWIND_Master_Project_Engineering_Specification.docx`) set the
requirement: a reconstruction engine in which every material claim points at
evidence, unknown is visually and textually distinct from confirmed, the interface
never implies that an inferred cause was observed, and all of it works without an
LLM (spec §8, §D3, §G).

## 2. Approach

Three commitments, made before any code (`docs/00-project-charter.md`,
`ROADMAP.md`):

1. **Simulated data.** A Blender warehouse, three cameras, four entity classes, six
   scripted cases at 720p / 10 FPS / 45 s, with frame-exact ground truth exported in
   the same `Observation` schema the detector emits (`docs/dataset/scene-spec.md`).
   Ground truth and prediction share a shape, so evaluation compares like with like,
   and there is no privacy or licence surface.
2. **Contract-first decoupling.** Ten Pydantic contracts, an event envelope and the
   evidence-level enum frozen in the first two days; golden fixtures at every
   boundary; a mock API serving them. Every later phase was written against a type and
   tested against a fixture, so the UI was built from Week 4 against a pipeline that
   did not exist, and the swap to the real API was a configuration change.
3. **A modular monolith** (`ADR-0001`), with the reasoning layer's schedule protected
   above everything else.

The evidence model is the spine. `EvidenceLevel` — confirmed, strongly inferred,
possible, conflicting, unknown — is carried by every claim, hypothesis and node, and
the phrasing available to the report generator is *derived* from it: "Observed",
"Likely contributed", "Possible", "Conflicting evidence", "Cannot determine". The
`Claim` contract rejects any claim above *unknown* that has no evidence reference,
and any claim whose text does not carry its level's phrase. The generator cannot
emit an uncited or over-stated claim; that is what "structural" means here.

## 3. System

`docs/03-architecture.md` has the diagrams. In one paragraph: a FastAPI process,
one arq worker, Postgres with pgvector, Redis, and a React UI behind nginx, in Docker
Compose. A run — footage plus dataset, config and model versions, identified by their
hash — is the unit of work. The worker runs ingestion, detection (`yolo11n-rewind-v3`),
tracking (ByteTrack per camera), event extraction, cross-camera association, incident
triggers, graph construction, ranking and report generation in order, committing after
each stage; every stage after perception reads the previous one's rows. Every version
string is stamped on the run.

Cross-camera identity scores time overlap, geometric plausibility and a colour
descriptor, and thresholds into `LINKED` or `UNKNOWN`. Refusing to link is a normal
outcome, scored on the false-link rate first: a wrong link manufactures a trajectory,
a refusal produces an honest gap.

The investigator UI (`apps/web`) has the eight screens of spec §G. Three video panes
share one clock through `requestVideoFrameCallback`, with per-camera offsets; every
selection anywhere — an event on the timeline, a node in the graph, a reference in
the report — seeks every camera to its moment. Evidence state is encoded on three
channels (colour, stroke pattern, label), contrast-checked, so unknown is
distinguishable from confirmed in greyscale.

Security (`docs/10-security-and-privacy.md`, `ADR-0009`, `ADR-0011`): a login page on a
session cookie, or HTTP Basic for scripts, with two roles;
analysts read every derived artefact and never a frame; investigators also stream
footage and make changes. Every read of footage, graph or report is an audit row and a
structured log event. Every report ends with the responsible-use statement.

## 4. Evaluation protocol

`docs/07-evaluation-plan.md`. Four cases to tune on, two sealed from E1.3 until
E9.1 and opened once. Every learned component measured beside a simpler baseline
(spec §D4): a COCO zero-shot detector against the fine-tuned one, geometry-and-time
association against association with colour. Two metrics are the project's thesis and
were defined before anything existed:

- **Evidence coverage** — material claims with at least one valid reference over
  material claims; *unknown* claims count as covered, because "cannot determine" is a
  supported statement about absent evidence.
- **Unsupported-claim rate** — claims whose references do not exist or do not
  support the stated level.

Gates were reviewed at each phase (`docs/gates/`), each with an honest-verdict line.
Floors were calibrated at Gate 1 from measured baselines, never from a golden number.
The golden run was pre-registered in a committed experiment record before it ran.

## 5. Results

### 5.1 Tune cases, at the gates

| Gate | Measure | Result |
|---|---|---|
| 1 | Detection recall / precision, person and robot | ≥ 0.987 on every pair (`case_05` validation) |
| 1 | ID switches per camera per case | ≤ 2 |
| 2 | Zone-event precision / recall, real pipeline | 0.88 / 0.92; timing error ≤ 0.2 s |
| 3 | Cross-camera false-link rate | 0.00 (0 of 20 links); recall 0.74 |
| 4, 5 | Cause ranking, evidence coverage, unsupported claims | top-1 3 of 3; 1.00; 0.00 |
| 6 | Fresh clone to running case from the README alone | passed twice, two bugs found and fixed on the way |

### 5.2 Held-out cases (EXP-0010), and after the fixes (EXP-0011)

| Metric | Floor | Held-out | Post-golden |
|---|---|---|---|
| Detection recall / precision, robot | ≥ 0.95 | 0.991 / 0.998 | same |
| Detection recall / precision, person | ≥ 0.95 | **0.065 / 0.875** | same |
| ID switches, worst camera | ≤ 2 | 2 | 1 |
| Zone-event precision / recall | ≥ 0.85 / 0.90 | **0.38 / 0.53** | **0.58 / 0.37** |
| Event timing error, max | ≤ 0.5 s | 0.40 s | 0.40 s |
| Cross-camera false-link rate | ≤ 0.05 | **0.25** | **0.29** |
| Cross-camera recall | ≥ 0.65 | **0.35** | **0.29** |
| Evidence coverage / unsupported-claim rate | ≥ 0.95 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| Gap recall | ≥ 0.90 | ≥ 0.995 | ≥ 0.995 |
| Cause top-1, detections (five incidents) | ≥ 0.67 | **0.60** | **0.60** |
| Cause top-1, perfect tracks | — | 0.80 | 0.80, both golden causes ranked |

The behaviours the golden cases exist for — the person's unseen interval named and
cited as *Cannot determine*, the person's entry worded no stronger than *Possible*,
both forklifts ranked in the ambiguous blocked-zone case — fail on the held-out run
for reasoning reasons (F3, F5, F6, F7), and after the fixes pass on perfect tracks. On
real detections the *Cannot determine* claim passes and the rest fail because the
entity is not detected (F1, F2).

### 5.3 What the numbers mean

The line between the two halves of the table is the finding. Every floor that fails
is a perception floor or downstream of one; every floor the reasoning layer owns
passes, on inputs it was never tuned on. Evidence coverage and the unsupported-claim
rate are perfect on every report the system has ever generated, because the contract
makes the alternative unrepresentable. Gap recall is near-perfect because gaps are
computed from what was observed, not inferred.

The perception failures are diagnosed to frames (`docs/failures/README.md`): a
forklift of a colour absent from the tune set is never detected (F1); a person at a
fifth of their silhouette is not found (F2, accepted as a visibility limit); a
duplicate box on a half-visible forklift seeds a track that is linked to the same
forklift on other cameras (F4). The postmortem
(`docs/incidents/2026-09-14-golden-perception.md`) traces all three to one root
cause: the tune/golden split was chosen for incident coverage and never checked for
appearance coverage.

### 5.4 Cost

EXP-0012: perception is 95 % of a run; 160–170 FPS on an Apple M4 with MPS, five
times real time; 12–16 FPS on CPU in a container. Peak memory 690 MB RSS plus 1.1 GB
accelerator. Every API endpoint under 20 ms warm. No parallelisation: one accelerator,
one detector, and threads would add contention and a non-deterministic frame order.

## 6. Engineering record

The plan was not followed; it was measured against. `docs/deviation-ledger.md` holds
59 classified departures: 16 improvements, 25 neutral, 4 bug-fixes, 14 debts of which
8 are repaid. Twelve experiment records, ten ADRs, seven gate reviews, a failure
catalogue with frames, a model card per checkpoint, and 327 automated tests including
failure tests (worker restart, corrupt clip, Redis down, missing camera), a golden
end-to-end test, and browser checks of replay sync and evidence navigation.

Three decisions worth a reader's attention. Ultralytics' AGPL licence was adopted
rather than worked around (`ADR-0002`). The database moved into the compose stack so
that a stranger's clone needs no account (`ADR-0007`), and the role boundary followed
it into the API for the same reason (`ADR-0009`). Kafka was declined twice, once on
prediction and once on measurement (`ADR-0001`, `ADR-0010`), with the triggers that
would reverse it written down.

The roadmap is in weeks; the build took seven calendar days. Every phase and gate
happened in order; the weekly mechanisms did not apply at that pace, and the audit
says so (`docs/audit/final-audit.md`).

## 7. Limitations

- **Perception generalises only as far as the tune cases' appearances reach.** F1 was
  closed after the fact: one added tune case with the missing forklift colour, and the
  same recipe, found it (0.930 recall against 0.259) while keeping everything v1 held
  (EXP-0013, `yolo11n-rewind-v3`, promoted). F2 stands: a person at a fifth of their
  silhouette is not detected, and EXP-0013 confirmed that is a visibility limit rather
  than a training gap. The lesson is the postmortem's, not the fix's: a split chosen
  for incident coverage and never checked for appearance coverage.
- **Cross-camera identity's held-out floor failure** (0.25 against 0.05) came from
  linking a fragment of a real forklift to that forklift; under v3 those links are gone
  and the rate is 0.00, but the layer still has no notion of "part of an entity I
  already know", which is also what F8 is. Cross-camera recall remains low (0.16–0.35),
  and refusing is the intended behaviour when it cannot be sure.
- **Simulated footage.** Untextured primitives, perfect lighting, no motion blur. The
  public-footage realism check (roadmap stretch 1) was not reached; nothing here
  claims transfer to real video.
- **Two incident classes, three cameras, one scene**, by charter.
- **No human validation.** The mentor walkthrough of C01 did not happen before the
  golden cases opened; the reproducibility test by a stranger has not been run.
- **Analytics** has no calendar trend: simulated footage carries no capture time.

## 8. Conclusion

A reconstruction system can be made structurally honest: not by asking a model to be
careful, but by making an uncited or over-stated claim impossible to represent, and
by treating what was not seen as evidence in its own right. On the cases it was tuned
on and on the cases it was not, REWIND's reports cite everything they say and say
nothing they cannot cite. What it cannot yet do is see well enough on unseen
appearances, and the record of that failure — pre-registered, traced to frames, fixed
beside the number and not in its place — is the part of this project most worth
keeping.

## Artefacts

| | |
|---|---|
| Source | the repository; `README.md` is the entry point |
| Architecture and data flow | `docs/03-architecture.md` |
| Dataset provenance | `docs/dataset/scene-spec.md`, `data/manifests/v1.1.json` (and `v1.json`, the golden run's), releases `data-v1.1` and `data-v1` |
| Experiments and model cards | `docs/experiments/`, `artifacts/model-cards/` |
| Evaluation report with baselines | `artifacts/benchmark-reports/final.md` |
| Failure catalogue | `docs/failures/README.md` |
| Decisions | `docs/adr/ADR-0001` … `ADR-0010` |
| Gates | `docs/gates/` |
| Audit and postmortem | `docs/audit/final-audit.md`, `docs/incidents/2026-09-14-golden-perception.md` |
| Demo script, presentation, future work | `docs/11-demo-script.md`, `docs/13-presentation.md`, `docs/14-future-work.md` |
