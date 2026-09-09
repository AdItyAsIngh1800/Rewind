# 07 — Evaluation Plan

- **Owner:** PS-7, extended at every gate
- **Entry point:** `make bench`
- **Output:** `artifacts/benchmark-reports/<timestamp>.md` — append-only

---

## 1. The principle

Every advanced method is compared against a simpler baseline. A complex model is never
presented merely because it is complex, and a number without a baseline beside it is
not a result.

Two metrics carry the project's actual argument. The rest are standard bookkeeping:

- **`false_link_rate`** — how often the identity layer invented a cross-camera
  connection that does not exist. A false link fabricates a trajectory and every
  downstream conclusion inherits it, which makes it strictly worse than a missed link.
  A system that refuses to link is not penalised.
- **`unsupported_claim_rate`** — how often a report states something it cannot point
  at. Target zero, and zero **structurally**: the `Claim` contract makes an uncited
  claim impossible to construct, so this metric exists to catch the remaining case of
  a citation that dangles.

## 2. What is measured

| Component | Metrics | Where |
|---|---|---|
| Detection | precision, recall, F1 at IoU 0.5 | `match_detections` |
| Tracking | ID switches | `count_id_switches` |
| Cross-camera identity | **false-link rate** | `false_link_rate` |
| Event extraction | precision, recall, F1, mean timing error | `match_events` |
| Cause ranking | top-1, top-3 against the annotated cause | `top_k_accuracy` |
| Evidence quality | **coverage**, **unsupported-claim rate** | `evidence_coverage`, `unsupported_claim_rate` |
| System | throughput, peak memory | `scripts/bootstrap/smoke_accel.py` |

IDF1 and HOTA arrive in E3.2 with real tracking output, via `motmetrics`. Implementing
them now against fixtures would be measuring nothing.

## 3. Thresholds

The provisional floors from charter §6 are encoded in
`packages/evaluation/benchmark.py` as `FLOORS` and `CEILINGS`, so the report renders a
PASS/FAIL verdict rather than leaving a reader to compare numbers by eye.

**These are replaced at Gate 1** with values calibrated against the measured baseline.
A floor may be lowered only alongside an experiment record explaining why it was
unreachable.

## 4. Why the harness scores 1.0 today

`make bench` currently scores the golden fixtures against themselves and passes
everything. That is the intended starting state, and the report says so in its own
header: it proves the plumbing works before any model exists, so when the first real
numbers arrive we already know the harness is not the thing that is wrong.

**A self-comparison proves nothing on its own** — a harness hard-wired to return 1.0
would also pass it. So `tests/unit/test_benchmark.py` deliberately damages the
predictions and asserts the right metric degrades:

| Damage introduced | Metric that must fall |
|---|---|
| Observations dropped | `detection_recall` |
| Boxes moved off-target | `detection_precision` |
| Events shifted five seconds late | `event_f1` |
| A cross-camera link fabricated | `false_link_rate` |
| A claim citing `EVT-9999` | `unsupported_claim_rate` |
| Hypothesis ranking reversed | `cause_top_1` |

Without those tests, "all metrics pass" is an unfalsifiable statement.

## 5. Split discipline

Four tuning cases, two golden cases held out. The golden pair is **not opened until
E9.1 in Week 17**, and no golden frame may enter any training or validation split.
This is asserted on case IDs in the split manifest, not checked by eye.

## 6. Reproducibility

Every report records dataset version, run id and device. Golden-benchmark comparisons
are never made across devices — MPS and CPU differ in the last decimals, and a
comparison that silently crosses hardware is not a comparison.

## 7. Usage

```bash
make bench                                   # self-check against the fixtures
uv run python scripts/evaluation/run_benchmark.py \
    --predicted artifacts/predictions/run-42 \
    --truth data/samples/gold \
    --strict                                 # non-zero exit if any metric fails
```

`--strict` is what a CI regression gate would call once real predictions exist.
