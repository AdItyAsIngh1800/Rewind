# REWIND — technical presentation

Fifteen slides, twenty minutes, five for questions. One idea per slide; the speaker
notes under each are what to say, not what to read. Screenshots for slides 6–10 come
from the demo recording (`docs/11-demo-script.md`).

---

### 1. REWIND

*Evidence-backed incident reconstruction for multi-camera video — with no language
model in the path.*

> Three cameras, a simulated warehouse, two kinds of incident. The system rewinds,
> reconstructs, ranks the causes, and writes a report that cites everything it says —
> and says "cannot determine" where it should.

### 2. The problem

- Video systems show footage; the question after an incident is *what happened, what
  caused it, what cannot be known from the recording*.
- An LLM asked that question answers fluently, and an inferred cause reads exactly
  like an observed fact.
- An interval no camera saw gets filled.

> The failure mode is not being wrong. It is being confidently indistinguishable from
> right.

### 3. The commitment

- Every material claim cites stored evidence, or it cannot exist.
- Unknown is visually and textually distinct from confirmed.
- The vocabulary is derived from the evidence level, never chosen.
- All of it without an LLM. (One could sit *behind* this. Never in front.)

### 4. The evidence model

```
confirmed → "Observed"          strongly_inferred → "Likely contributed"
possible  → "Possible"          conflicting       → "Conflicting evidence"
unknown   → "Cannot determine"
```

- Carried by every claim, hypothesis and graph node.
- The `Claim` contract rejects a claim above *unknown* with no reference, and any
  text that lacks its level's phrase.

> "Structural" means the generator cannot emit the bad sentence. Not "was asked not
> to".

### 5. The pipeline

Diagram from `docs/03-architecture.md` §2.

ingest → detect → track → events → identity (LINK or **UNKNOWN**) → incident + rewind
window → evidence graph with provenance → ranked causes with support **and
contradiction** → deterministic report.

> One worker, one process, commit after each stage; every stage reads the previous
> one's rows. Every version string is stamped on the run.

### 6. Synchronized replay

Screenshot: three panes, one clock.

> Per-camera clock offsets; `requestVideoFrameCallback`; every selection anywhere on
> the page seeks every camera. Clicking evidence is how you check the system.

### 7. The evidence graph

Screenshot: graph with a hatched GAP node selected; inspector showing provenance.

> Entities, observations, events, locations, gaps, conflicts. Every node and edge
> points at a stored row. Postgres with recursive CTEs, not a graph database.

### 8. The report

Screenshot: claims with levels and references; hypotheses with support and
contradiction refs; limitations ending with the responsible-use sentence.

> Coverage 1.00, unsupported 0.00, on every report the system has ever generated.

### 9. The UNKNOWN interval

Screenshot: `case_02` timeline, *Unseen / undecided* lane; the *Cannot determine*
claim citing the gap.

> The person is behind the forklift. No camera has them. The system names the
> interval, cites it, and lowers everything that depends on it. This is the thesis.

### 10. Evaluation protocol

- Four tune cases; two sealed from day 3 to E9.1, opened once.
- Pre-registered: the experiment record committed before the run.
- Every learned component beside a simpler baseline.
- Fixes go *beside* the held-out number. Never in its place.

### 11. Results — the two halves

| Reasoning layer, held out | | Perception layer, held out | |
|---|---|---|---|
| Evidence coverage | **1.00** | Person recall | **0.065** |
| Unsupported claims | **0.00** | Forklift F02 found | **0 of 697** |
| Gap recall | **≥ 0.995** | False-link rate | **0.25** (floor 0.05) |
| Cause top-1, perfect tracks | **0.80** | Zone-event recall | **0.53** |

> Every floor that fails is a perception floor. Every floor the reasoning layer owns
> passes on inputs it never saw. Eight of fifteen floors fail; all eight are traced to a
> frame.

### 12. Why perception failed

Frames: F1 (navy forklift, no box) and F2 (a fifth of a person beside a forklift).

> The tune/golden split was chosen for incident coverage and never checked for
> appearance coverage. A detector trained on three cases learned *forklift* as one
> colour. The sealed discipline that made the benchmark honest hid the gap until it
> could not be fixed without contaminating the result. Postmortem in the repo.

### 13. Engineering record

- 59 classified deviations from the plan; 14 debts, 8 repaid.
- 12 experiment records, 10 ADRs, 7 gate reviews with an honest-verdict line.
- 327 tests: unit, integration, API, failure (worker restart, corrupt clip, Redis
  down, missing camera), golden end-to-end, browser.
- `docker compose up` from a fresh clone, twice.

> The plan was not followed. It was measured against.

### 14. Decisions worth defending

- Modular monolith, and no Kafka — twice, once on prediction, once on measurement
  (ADR-0001, 0010).
- AGPL inherited from Ultralytics rather than worked around (ADR-0002).
- Database and role boundary brought local so a stranger's clone needs no account
  (ADR-0007, 0009).
- Fine-tune, never from scratch (ADR-0004).

### 15. What is next, and what to take away

- A tune case with the second forklift colour; retrain; measure beside EXP-0010.
- Public-footage realism check. Re-ID embeddings. An LLM *behind* the template, with
  an unsupported-claim regression test against it.

> Take away one sentence: honesty in a reconstruction system can be structural. Make
> the uncited claim unrepresentable, and treat what was not seen as evidence.

---

## Likely questions

- *Why simulated?* Frame-exact ground truth in the detector's own schema; repeatable
  incidents; no privacy surface. The cost is realism, and the report says so.
- *Isn't 0.065 person recall disqualifying?* It fails the floor and the report says
  so first. It is a visibility-threshold and dataset-coverage failure, traced to
  frames; the reasoning layer's numbers are unaffected because they are measured on
  perfect tracks too.
- *Why not an LLM?* Spec §D3 requires the engine to work without one. One could
  consume the graph and produce prose, behind the template, with the template as
  fallback and a regression test comparing unsupported-claim rates. Stretch item 2.
- *Why HTTP Basic?* Two roles, no user management by charter, a `<video>` element
  that cannot carry a bearer token. ADR-0009 has the alternatives and the TLS caveat.
- *Twenty weeks in seven days?* Every phase and gate in order; the calendar
  mechanisms did not apply. The audit says so on its first page.
