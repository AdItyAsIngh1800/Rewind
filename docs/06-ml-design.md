# ML design

The learned and tuned components, what each was compared against, and where the
numbers are. Every decision here has an experiment record under `docs/experiments/`;
this page is the index, not the evidence.

## 1. Principle: every learned component beside a simpler one

Spec §D4. Nothing learned was adopted without a measured baseline next to it, and the
baseline column is kept in `artifacts/benchmark-reports/final.md` for the held-out
cases.

| Component | Baseline | Adopted | Why the baseline lost |
|---|---|---|---|
| Detector | COCO `yolo11n.pt`, zero-shot | `yolo11n-rewind-v1`, fine-tuned | Zero-shot scores 0 on every class: the scene's entities are untextured primitives, not photographs (EXP-0001, `ADR-0004`). |
| Tracker | ByteTrack defaults | ByteTrack, `match 0.9`, NMS `0.5` | Default `match_thresh` reads backwards in Ultralytics (it bounds IoU *distance*); NMS 0.7 detected one person twice from an elevated camera (EXP-0002, 0004). |
| Cross-camera appearance | geometry and time only | + colour-histogram descriptor | One pair net on the tune cases, and it swings both ways; kept because the false-link rate stayed 0 there (EXP-0007). On the golden pair it added two false links (EXP-0010, F4). |
| Report | — | deterministic template | An LLM is a stretch item, never in front of the template (`ADR-0001`, spec §D3). |

## 2. Detector

`yolo11n-rewind-v1`: YOLO11n, pretrained initialisation, 20 epochs, 860 s on MPS, on
`case_01`, `03`, `04`; validated on `case_05`, the negative case; `case_02` and
`case_06` never seen before E9.1. Ground truth is ray-cast from the Blender scene
under the visible-box convention (`docs/dataset/scene-spec.md`).

| | Tune (EXP-0003) | Held-out (EXP-0010) |
|---|---|---|
| mAP50 | 0.987 | — |
| Robot recall / precision | — | 0.991 / 0.998 |
| Person recall / precision | — | 0.065 / 0.875 (F2: ground truth counts the person from 15 % visibility; a fifth of a silhouette behind a vehicle is not found) |
| Forklift recall, case_06 | — | 0.259 (F1: the second forklift's colour is absent from the tune set) |
| Pallet recall / precision | 0.999 / 1.000 | 0.971 / 0.986 |

The model card, with limitations per checkpoint, is
`artifacts/model-cards/yolo11n-rewind-v1.md`. A `v2` trained with colour-blind
augmentation (EXP-0011, F1) finds the second forklift but loses `case_02`'s frame-cut
forklift and was **not promoted**; the honest fix is a dataset one (a tune case with
that colour), owed as an E1 re-render.

Hardware: Apple M4, MPS, batch 8; 160–170 FPS through perception, 1.1 GB accelerator
memory (EXP-0012). The CPU container image runs the same weights at 12–16 FPS.

## 3. Tracking

ByteTrack per camera, as bundled with Ultralytics, at 10 FPS. Tuned on perfect boxes
first (EXP-0002), then on real detections (EXP-0004): ID switches ≤ 2 per camera per
case on tune, 2 then 1 on held-out. Long-gap identity is not the tracker's job here:
after seconds unseen the Kalman prediction has drifted, so re-identification across a
gap is left to the cross-camera layer, which can refuse.

## 4. Cross-camera identity

Score = weighted time overlap, geometric plausibility, colour similarity
(`w0.35/0.4/0.25`), thresholded at 0.75 into `LINKED` or `UNKNOWN`, with an ambiguity
margin of 0.1 that refuses a link when two candidates are close. Refusing is a normal
outcome and is scored as such: the primary metric is the **false-link rate** (floor
≤ 0.05), never recall. Tune: 0 false links in 62 decisions. Held-out: 0.25 (2 of 4 on
`case_02`), the largest single miss of the benchmark. F4's fix (EXP-0011) removed the
duplicate box that seeded one of the linked tracks but not the links: the remaining
ones join a fragment of the real forklift, seen alone at the frame edge, to that same
forklift on other cameras — no trajectory between two different entities is invented,
and the metric counts it anyway. Measured beside, not instead of, the held-out figure.

## 5. Events, incidents, reasoning

Not learned: rule-based over geometry primitives (`packages/common/geometry.py`,
unit-tested near 100 %), with thresholds chosen on tune cases and recorded on the run.
Events (EXP-0005, 0006): lossless on perfect tracks; a 1.0 s merge window was the
Gate 2 blocker, not perception. Incidents (EXP-0008): both classes, asymmetric windows,
every window contains its cause. Reasoning (EXP-0009): right about *what* on every
tune incident; the residual errors under-claim rather than over-claim.

## 6. Evaluation protocol

`docs/07-evaluation-plan.md`. Two cases sealed from E1.3 to E9.1 and opened once
under a pre-registered protocol (EXP-0010, committed before the run). Every later fix
is post-golden, measured beside the held-out number, never replacing it (EXP-0011),
and no threshold was tuned on a golden figure. The failure catalogue with frames is
`docs/failures/README.md`.

## 7. What was not done, and why

- **Re-ID embeddings** (OSNet, CLIP crops): the colour histogram was to be measured
  first (roadmap E5.2); it was, and the identity layer's held-out failures are about
  geometry across a gap, not about descriptors. Future work.
- **Detector from scratch**: `ADR-0004`.
- **Parallel perception**: EXP-0012 shows one accelerator, one detector; threads add
  contention, not throughput.
- **A tracked-perfect harness mode** (perfect detections through the real tracker):
  owed since EXP-0011; it would separate tracking loss from detection loss on the
  golden pair.

## Related

`docs/experiments/` · `artifacts/model-cards/` · `artifacts/benchmark-reports/final.md`
· `docs/failures/README.md` · `ADR-0004` · `docs/07-evaluation-plan.md`.
