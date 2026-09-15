# Final audit

Roadmap Part 3.3, written at the end of E10 with every gate reviewed. Four parts: the
Definition of Done line by line, the deviation ledger's debt, the specification against
what exists, and the two checks only other people can run. The postmortem is
`docs/incidents/2026-09-14-golden-perception.md`.

One fact frames everything below. The roadmap is written in weeks; the build took
**seven calendar days** (2026-09-09 to 2026-09-15, 245 commits). Every phase, gate and
experiment happened in the roadmap's order, but the calendar mechanisms — weekly logs,
gate dates, Friday drift checks — did not apply at that pace. The deviation ledger
served as the drift check; the gate reviews are dated by phase, not by week; there is
one weekly log. Recorded here rather than dressed up.

## 1. Definition of Done — specification §P

| # | Line | Verdict | Evidence |
|---|---|---|---|
| 1 | Three camera clips can be ingested and processed | **Met** | Six cases of three clips through the compose stack (`docs/gates/gate-6.md`); a run records probe metadata, offsets, input hash (`services/ingestion/`). |
| 2 | Detection and tracking meet the benchmark threshold | **Partially met** | Tune cases: every Gate 1 floor met (`docs/gates/gate-1.md`). Held out: robot 0.991/0.998 and ID switches ≤ 2 pass; person recall 0.065 fails (F2, accepted occlusion limit), forklift F02 never detected (F1, colour absent from tune data). `artifacts/benchmark-reports/final.md`. |
| 3 | Events are timestamped and queryable | **Met** | `GET /cases/{id}/timeline?start_s&end_s`; timing error ≤ 0.4 s on every case (EXP-0006, 0010). |
| 4 | At least one incident class is automatically detected | **Met** | Both classes, from video events and robot telemetry; every tune and golden incident opened, negative case silent (EXP-0008, 0010). |
| 5 | An investigation window is created automatically | **Met** | Asymmetric rewind window on every incident; every window contains its cause (EXP-0008). |
| 6 | Cross-camera evidence is assembled | **Partially met** | Identity links with explicit refusals, scored on false-link rate first. Tune: 0 false links in 62 decisions. Held out: 0.25 against a floor of 0.05 (F4; the links join a fragment of the real forklift to itself). |
| 7 | Evidence graph is generated | **Met** | Provenance on every node and edge; gap and conflict nodes; Postgres, no graph database (`ADR-0005`, EXP-0009). |
| 8 | Cause hypotheses are ranked | **Met** | Ranked with support and contradiction refs. Top-1 0.80 on perfect tracks, 0.60 on detections across five incidents; both golden causes ranked post-golden on perfect tracks. |
| 9 | Unknown/occluded intervals are explicit | **Met** | Gap recall ≥ 0.995 on the golden pair; every gap a node, a hatched interval in the UI, and a *Cannot determine* claim citing it (F6, EXP-0011). |
| 10 | Investigator UI supports replay and timeline inspection | **Met** | Three panes on one clock with per-camera offsets; every selection seeks every camera; `make ui-check` 7/7 in Chrome. |
| 11 | Report is evidence-grounded | **Met** | Evidence coverage 1.00 and unsupported-claim rate 0.00 on every report ever generated; structurally enforced by the `Claim` contract; vocabulary bound to the evidence level. |
| 12 | Critical logic has automated tests | **Met** | 327 tests: unit (geometry, timestamps, evidence states, auth), integration (ingest → observation → event → incident, failures: worker restart, corrupt clip, Redis down, missing camera), API (contract, idempotency, authorization), e2e (golden case → expected timeline), browser (replay sync, evidence navigation). Load tests not written — see §3. |
| 13 | Benchmark results and failure cases are documented | **Met** | `final.md` with held-out and post-golden columns, twelve experiment records, `docs/failures/README.md` with frames, a model card per checkpoint. |
| 14 | Repository can be started from the README | **Met** | Two fresh-clone runs (`docs/gates/gate-6.md`); needs Docker, uv and `gh auth login` for the private data asset. |
| 15 | Architecture, ML, security, evaluation and deployment documentation are complete | **Met** | `docs/03-architecture.md`, `06-ml-design.md`, `07-evaluation-plan.md`, `09-deployment.md`, `10-security-and-privacy.md`; ADR-0001–0010. |

Thirteen met, two partially met, none unmet. Both partials are perception floors on
unseen data, and both are diagnosed to a frame: `docs/failures/README.md` F1, F2, F4.

## 2. Deviation ledger — the debt

59 rows: 16 `IMPROVEMENT`, 25 `NEUTRAL`, 4 `BUG-FIX`, 14 `DEBT` of which 8 are repaid.
Open debt, and what each costs the reader of the final report:

| Row | Debt | State |
|---|---|---|
| PS-2 disk | 32 GB free against a 200 GB plan | Open; never bit. Render passes are not persisted. |
| PS-2 worker | Container image is CPU-only; Docker has no Metal access | Accepted: a hardware fact (`docs/09-deployment.md`). |
| E4.2 | Golden cases' zone-event scores seen once before E9.1 | Open by nature; no threshold was set from them, recorded so the reader can weigh it. |
| E8.6 | Analytics has no calendar trend or pattern by location | Open. `captured_at` is on the contract (`ADR-0006`) but simulated footage has no capture time; set it at ingestion when real footage arrives. |
| E7.5 | Mentor walkthrough of C01 not held before the golden cases opened | Open; §4 below. |
| E10.1 | Container CPU throughput is 12–16 FPS against 63 FPS on the host's CPU | Open. Thread count and BLAS are the suspects; a batch reconstruction tool is usable at half real time, so it was not chased. |
| E10.1 | Worker speed misreported once, corrected the same day | Closed by the correction row; kept because it happened. |

Repaid: the frozen-actor render, the rerouted waypoints, Gate 6's hosted-credential
requirement (`ADR-0007`), the replay and click-to-seek deferrals (E8.2/E8.3, repaid
2026-09-14), the clip references on the run (`ADR-0006`), the `yolo11n.pt` history
scrub, and the CI image build (added at the close).

## 3. Specification against what exists

What the master specification promised, what is there, and the one-line reason for
each gap. Everything not listed matches.

| Spec | Promised | Built | Why the gap |
|---|---|---|---|
| §B1 | RTSP/live input as a later milestone | Prerecorded clips only | Charter non-goal; `ADR-0010` trigger 4. |
| §B1 | Case reprocessing with another model/config version | `POST /cases/{id}/reprocess` under another config version | Model selection per run not built: the worker loads one checkpoint. |
| §B1 | Audit trail of report revisions | Reports immutable; a revision is a new run's report beside the old | Same intent, simpler mechanism. |
| §C | Kafka or Redpanda "after MVP" | None | `ADR-0010`. |
| §C | Local filesystem → S3-compatible storage | Filesystem; Supabase buckets defined, unused | Nothing needed object storage at six cases (`ADR-0006`). |
| §C | Grafana / OpenTelemetry later | JSON logs, `/metrics`, System Health | Stretch; not reached. |
| §C, §L | Playwright | agent-browser driving Chrome | Same checks, one dependency fewer; ledger 2026-09-14. |
| §C | FastAPI WebSockets | Polling (TanStack Query, 10 s on System Health) | Nothing needed push at this scale. |
| §D | Re-ID embedding after the colour baseline | Colour baseline measured; embedding not tried | E5.2 said measure the cheap one first; its failures are geometric, not descriptor. |
| §G | Analytics by location and over time | By class and review outcome | No calendar time on simulated footage; no zone on incidents. |
| §H | RTX 4050, CUDA | Apple M4, MPS; CPU in containers | `docs/09-deployment.md` §1 supersedes §H. |
| §I | `docs/01`, `02`, `04`, `05`, `08`, `10-runbooks` | `00` charter, `03`, `06`, `07`, `09`, `10-security`, `11-demo`; contracts are `packages/schemas/README.md` + `openapi.json` | Numbering followed where a document was needed; the spec itself is `01`/`02`. |
| §I | `infra/aws`, `infra/monitoring`, `ml/notebooks` | READMEs only | Cloud and dashboards are stretch; no notebook was needed. |
| §J | Twenty weeks | Seven days, phases in order | See the note at the top. |
| §L | Load tests at increasing event/API rates | Not written | Every endpoint under 20 ms warm (EXP-0012); no rate to load against. |
| §L | ML regression: golden benchmark per release | `make bench` and EXP-0010/0011 by hand; not a CI job | Needs the rendered data in CI (38 MB private asset); one afternoon. |
| §O4 | Weekly logs | One (`docs/weekly/week-00.md`); the ledger did the job | Pace. |
| §Q | Demo video, presentation, academic report | Script, deck and report written (`docs/11-demo-script.md`, `12`, `13`); video not recorded | §4. |

## 4. What only other people can do

- **Reproducibility test.** Hand the repository to someone else with `gh` access and
  Docker; they follow `README.md` only. Two fresh-clone runs by the author passed
  (`docs/gates/gate-6.md`); a stranger's run is the test the roadmap asks for.
- **Mentor walkthrough** of C01 with `docs/gates/gate-4-5-walkthrough.md`. Any change
  it prompts is post-golden.
- **Demo recording** from `docs/11-demo-script.md`; **presentation** from
  `docs/13-presentation.md`.

## 5. Honest verdict

Every gate was reviewed, and Gate 7 was recorded as a pass on its criterion while the
system fails the charter's perception floors on unseen data. That is the sentence a
reader should carry: the reasoning layer — the graph, the ranking, the gaps, the
report — does what the charter asks on inputs it was never tuned on, and the perception
layer under it does not yet generalise to an appearance it never saw. Both are
measured, both are traced to frames, and the fixes are beside the held-out numbers,
not in their place.
