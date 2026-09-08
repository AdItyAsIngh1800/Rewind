# Risk register

Sixteen challenges carried over from the master specification §K, plus the two this
build has added. Reviewed every Friday as part of the weekly log.

**Escalation rule:** when a risk hits its trigger, it is addressed the following week.
Not "soon".

| # | Risk | Likelihood | Impact | Early-warning signal | Mitigation | Escalation trigger |
|---|---|---|---|---|---|---|
| R1 | Unified-memory pressure | Medium | High | Sudden throughput collapse — Metal pages to disk rather than raising OOM | Compact models, batch 1, one heavy workload at a time, `empty_cache()` between runs | Inference throughput drops more than 5x between identical runs |
| R2 | Limited real incident data | Resolved | — | — | Simulated dataset with exact ground truth | Public-footage check (stretch 1) fails to generalise |
| R3 | Cross-camera ID switches | High | High | False-link rate rising while recall improves | Appearance + time + geometry; conservative threshold; explicit UNKNOWN | False-link rate > 0.05 at Gate 3 |
| R4 | Camera synchronization drift | Medium | High | Sync test fails on injected offset | Timestamp normalization, per-camera offset config, injected-offset test | Event ordering wrong across cameras |
| R5 | Occlusion | Certain | Medium | — | Use other cameras; mark the gap; never force a conclusion | A gap is silently filled rather than reported |
| R6 | False causal certainty | Medium | **Critical** | Report language stronger than evidence level | Rank hypotheses; vocabulary bound to the evidence enum | Any unsupported claim reaches a report |
| R7 | LLM hallucination | Low | High | — | LLM is stretch-only and sits behind the evidence graph | LLM output diverges from the template on the same evidence |
| R8 | Latency | Medium | Low | Report generation over 60 s on a case | Async jobs, frame sampling, cache derived records | Investigation feels unusable in the demo |
| R9 | Distributed-system complexity | Resolved | — | — | Modular monolith (`ADR-0001`) | A trigger in ADR-0001 §Validation fires |
| R10 | Database growth | Low | Low | Observation table dominating disk | Keep canonical events; compact low-value observations | Local disk pressure |
| R11 | Privacy / licensing | Resolved | — | — | Fully simulated footage; no real people | Any real footage enters the repo |
| R12 | False positives | Medium | Medium | Alert burden on the tuning set | Tune against validation split; report alert burden | Precision below floor at Gate 6 |
| R13 | False negatives | Medium | High | Recall dropping while precision is tuned | Recall-oriented benchmark plus secondary rule checks | A golden case incident is missed entirely |
| R14 | Scope creep | **High** | High | Ideas arriving without a ledger row | Strict charter §4; post-MVP backlog | Any week where a non-goal gets built |
| R15 | Frontend time sink | High | Medium | UI day/week consistently overrunning | Replay and timeline first; graph polish last | UI eats a phase that is not E8 |
| R16 | Cloud cost | Resolved | — | — | Local-first; cloud is stretch only | Any recurring charge appears |
| R17 | Hardware mismatch | Resolved | — | — | Retargeted to Apple Silicon / MPS in PS-2; spec §H superseded | An MPS operator gap blocks a required op with no CPU fallback |
| R19 | **Disk headroom** | **High** | High | 32 GB free against a spec assuming 200 GB | Blender passes consumed in-process, never persisted; prune Docker cache; compact derived observations | Free space below 15 GB |
| R20 | Docker has no Metal access | Certain | Medium | — | Worker runs on the host in development; container image is CPU-only for CI and the Gate 6 clone test | Gate 6 requires GPU parity inside the container |
| R18 | **Blender authoring effort** | Medium | High | Scene build running past Week 2 | Use CC0 assets; never model an asset by hand | E1.1 not done by end of Week 2 |

## Gate calendar

| **Gate 1** | E3.4 | Video reliably becomes timestamped observations | Week 7 | **Tue 03 Nov 2026** |
| **Gate 2** | E4.4 | Observations become correct semantic events | Week 9 | **Tue 17 Nov 2026** |
| **Gate 3** | E5.4 | Events can be connected across cameras | Week 11 | **Tue 01 Dec 2026** |
| **Gate 4** | E7.5 | An incident can be reconstructed without an LLM | Week 14 | **Tue 22 Dec 2026** |
| **Gate 5** | E7.5 | Every conclusion is evidence-traceable | Week 14 | **Tue 22 Dec 2026** |
| **Gate 7** | E9.1 | Benchmark results and failure modes are measurable | Week 17 | **Tue 12 Jan 2027** |
| **Gate 6** | E10.1 | A new developer can run the system from the repository | Week 19 | **Tue 26 Jan 2027** |

## The honest-verdict rule

At every gate, after the criteria are checked, one more question is answered **in
writing**:

> Is this gate genuinely passed, or am I passing it because it is on the calendar?

A failed gate is a valid outcome. Record it, then decide explicitly: fix, descope, or
accept and document the limitation. Proceeding while pretending is the only wrong move.
