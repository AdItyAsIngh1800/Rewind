# ADR-0004: Fine-tuning a pretrained detector on synthetic data is in scope

- **Status:** Accepted
- **Date:** 2026-09-09
- **Clarifies:** `docs/00-project-charter.md` §4 non-goals

## Context

E3.1 (Weeks 5–7) was written assuming a COCO-pretrained compact YOLO would detect the
four frozen entity classes. Verified against `yolo11n.pt` on 2026-09-09, it does not:

| Charter class | COCO coverage |
|---|---|
| `person` | Clean |
| `forklift` | Only via `truck` — a poor proxy for a warehouse forklift |
| `robot` | **No class exists** |
| `pallet` | **No class exists** |

One of four classes is cleanly covered. Without a change, `ROBOT_ESTOP_HUMAN_INCURSION`
cannot be reconstructed at all, because the robot — one of its two participants — is
undetectable.

The charter's non-goals include "training a detector from scratch". Read loosely, that
could be taken to forbid the obvious fix. This ADR states the distinction explicitly
rather than leaving it to be argued about in Week 6.

## Decision

**Fine-tuning a pretrained detector on the synthetic dataset is in scope. Training a
detector from scratch remains out of scope.**

These are different activities, and the non-goal targets the second:

| | From scratch | Fine-tuning |
|---|---|---|
| Initialisation | Random weights | COCO-pretrained weights |
| Data required | Order of 100,000+ labelled images | Order of 8,000 frames, which we generate |
| Time | Days to weeks | Under an hour on the measured hardware |
| Risk | High — a research project inside a systems project | Low — a standard adaptation step |
| What it claims | "We built a detector" | "We adapted a detector to our entities" |

The non-goal exists to stop the project turning into a detector-research project. Fine-
tuning does not do that. It is, in fact, the payoff for the dataset decision: simulated
data was chosen precisely because it yields perfect labels for free, and declining to
use them would waste the reason for choosing it.

### How it is done

- Fine-tune `yolo11n` on the **four tuning cases only**. The two golden cases are not
  touched until E9.1, and not for training at any point.
- Within the tuning cases, three for training and one held out for validation and early
  stopping.
- Augmentation is YOLO's standard frame-level transforms — mosaic, HSV jitter, flips.
  This does **not** conflict with the scene spec's constant-lighting rule: that rule
  fixes the *rendered scene* so detection failures are attributable, whereas
  augmentation is a training-time transform applied to frames after rendering.
- The fine-tuned model gets a **model card** recording purpose, data, metrics,
  limitations and version, as required for any promoted model.

### The baseline is still reported

Specification §D4 requires every advanced method to be compared against a simpler one.
The benchmark table must carry both:

1. **COCO-pretrained, zero-shot** — `person` only, the honest floor.
2. **Fine-tuned** — all four classes.

Reporting only the fine-tuned number would hide how much of the result came from
adaptation rather than from the pipeline.

## Alternatives considered

| Option | Why not |
|---|---|
| Open-vocabulary detector (YOLO-World, OWLv2, GroundingDINO) | Avoids the charter question entirely, but adds a heavy dependency, is less reliable on synthetic renders, and produces no baseline-versus-improved result worth writing up. |
| Detect `person` and `robot` only; treat forklift and pallet as known static objects | Smallest change, but the forklift is the *mobile occluder* that makes `C02` and `C03` work. Removing it from detection breaks the occlusion cases that carry the project's central claim. |

## Consequences

**Gained.** All four classes become detectable. The dataset decision pays off visibly.
There is a genuine, reportable ML result with a fair baseline beside it.

**The honest limitation, stated plainly.** Fine-tuning on synthetic frames and
evaluating on synthetic frames is a closed loop. All six cases share one scene, so the
detector will have seen this exact warehouse, this lighting and these assets. Detection
scores will look excellent and will say **almost nothing about real-world performance**.

That is defensible — a fixed-camera facility deployment genuinely is fine-tuned per
site, so the setup mirrors reality — but it must be written into the model card and the
evaluation report rather than quietly enjoyed. Stretch item 1, the public-footage check
on WILDTRACK or MMPTRACK, is the only thing in the plan that would actually test
generalisation, which raises its value.

**Schedule.** Adds roughly half a day to E3.1. The measured 10x throughput headroom
absorbs the training cost comfortably.

## Amendment, 2026-09-10: the zero-shot floor is uninformative on primitives

Measured rather than assumed. The COCO-pretrained checkpoint detects **nothing** in
the rendered scene — zero recall on all four classes, including `person`, which COCO
does cover.

The cause is not the missing classes this ADR was written about. It is that the
entities are currently untextured primitives, and a rectangular box is not
recognisable as a person. The same checkpoint on a photorealistic reference image of
the same four entities returns `person`, `truck` and `car`, which confirms the model
is working and isolates the cause to the geometry.

**What this changes.** The zero-shot number is still recorded, but it is not a
baseline in the sense this ADR originally intended. A comparison reading
"0.00 → 0.95" would look like a spectacular result while measuring only that boxes
are not people. Reporting it as baseline-versus-improved would overstate what
fine-tuning contributed.

**The honest claim.** Fine-tuning is measured as *detection ability* on the four
entity classes — precision, recall and F1 per class against ground truth — not as
adaptation over a pretrained baseline. The final report must say so in those terms.

**This is not a permanent limitation.** Nothing about the fine-tuning method depends
on it: only the input images change. The moment realistic assets replace the
primitives, whether from the stretch backlog or later, the zero-shot floor becomes
meaningful again and the original baseline-versus-improved comparison works exactly
as written above, with no methodological change and no retraining design to redo.

**Why the primitives stay for now.** Bringing the asset swap forward would reverse
the decision made deliberately in E1: primitives exist so that a
render-to-ground-truth-to-validate bug costs an afternoon rather than two weeks. That
protection is still wanted, and the evidence graph in weeks 13 and 14 is where the
schedule needs to be spent.

## Validation plan

- Fine-tuned model meets the Gate 1 recall floor (≥ 0.90 for `person` and `robot`).
- The benchmark table shows both the zero-shot figure and the fine-tuned result, with
  the zero-shot row annotated as uninformative on primitives rather than presented as
  a baseline.
- No golden-case frame appears in any training or validation split. This is checked by
  asserting on case IDs in the split manifest, not by inspection.

## Related

`docs/00-project-charter.md` §4 · `ROADMAP.md` E3.1 · specification §D2, §D4.
