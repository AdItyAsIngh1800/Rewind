"""Generate a model card for a promoted checkpoint.

Every promoted model gets a card recording purpose, data, metrics, limitations and
version (specification §O). The card is generated from the training record and the
evaluation JSON rather than written by hand, so the numbers on it are the numbers
that were measured and cannot drift from them.

The limitations section is the part that earns its place. A card that only lists
what the model does well is marketing; the point of writing one is that the next
person knows what it cannot do before they rely on it.

    uv run python scripts/ml/model_card.py --name yolo11n-rewind-v1 \
        --evaluation artifacts/benchmark-reports/detection-finetuned-case_05-<stamp>.json \
        --golden artifacts/benchmark-reports/detection-finetuned-case_02-<stamp>.json ...

`--golden` adds the held-out numbers once E9.1 has produced them. Limitations found on
those cases are prose, and prose specific to one checkpoint belongs beside its training
record: `ml/models/<name>/limitations.md` is appended verbatim when present.
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
from typing import Any

from scripts.ml.export_yolo_dataset import TRAIN_CASES
from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

MODELS = pathlib.Path("ml/models")
CARDS = pathlib.Path("artifacts/model-cards")


def _class_rows(per_class: dict[str, Any]) -> str:
    """Render one evaluation's per-class rows, marking classes the case lacks."""
    rows = []
    for cls, m in per_class.items():
        if m["truth"] == 0:
            rows.append(f"| `{cls}` | 0 | — | — | — |")
            continue
        rows.append(
            f"| `{cls}` | {m['truth']} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} |"
        )
    return "\n".join(rows)


def _golden_section(golden: list[dict[str, Any]], post_golden: str | None) -> str:
    """Render the golden cases: held-out for the checkpoint that met them sealed, post-golden after.

    A checkpoint trained after EXP-0010 cannot call these numbers held-out, whatever it
    scores: the cases were open when its data was designed. The card says which it is.
    """
    if not golden:
        return ""
    if post_golden:
        parts = [f"## Golden cases, post-golden ({post_golden})\n"]
        parts.append(
            "`case_02` and `case_06` were opened in EXP-0010 before this checkpoint's data "
            "existed, so these are not held-out numbers. They are measured beside the "
            "held-out ones in `artifacts/benchmark-reports/final.md`, never in their place.\n"
        )
    else:
        parts = ["## Held-out (E9.1)\n"]
        parts.append(
            "The golden cases were opened once, under EXP-0010's pre-registration, after the "
            "checkpoint was fixed. These are the only numbers on this card that neither "
            "trained nor selected the model.\n"
        )
    for ev in golden:
        parts.append(f"`{ev['case_id']}` ({ev['frames_processed']} frames):\n")
        parts.append("| Class | Truth | Precision | Recall | F1 |\n|---|---|---|---|---|")
        parts.append(_class_rows(ev["per_class"]) + "\n")
    return "\n".join(parts) + "\n"


def render(
    training: dict[str, Any],
    evaluation: dict[str, Any],
    zero_shot: dict[str, Any] | None,
    golden: list[dict[str, Any]] | None = None,
    limitations: str = "",
    post_golden: str | None = None,
) -> str:
    """Render the card as markdown."""
    name = training["name"]
    per_class = evaluation["per_class"]

    rows = []
    unmeasured: list[str] = []
    for cls, m in per_class.items():
        # 0/0 truth scores as a perfect 1.000 in the evaluation JSON. Printing that
        # would claim a measurement that never happened; the row says so instead.
        if m["truth"] == 0:
            unmeasured.append(cls)
            rows.append(f"| `{cls}` | 0 | — | — | — | not present in the evaluation case |")
            continue
        zs = ""
        if zero_shot is not None and cls in zero_shot["per_class"]:
            zs = f"{zero_shot['per_class'][cls]['recall']:.3f}"
        rows.append(
            f"| `{cls}` | {m['truth']} | {m['precision']:.3f} | {m['recall']:.3f} | "
            f"{m['f1']:.3f} | {zs} |"
        )
    table = "\n".join(rows)
    unmeasured_note = ""
    if unmeasured:
        names = ", ".join(f"`{c}`" for c in unmeasured)
        unmeasured_note = (
            f"\n\n**Unmeasured classes: {names}.** The evaluation case contains none of "
            "them, so this card makes no claim about their detection at all. "
            + (
                "Their only independent numbers are in the held-out section."
                if golden
                else "The first independent number for them arrives in E9.1 from the golden cases."
            )
        )

    zero_shot_note = ""
    if zero_shot is not None:
        zero_shot_note = (
            "\nThe zero-shot column is the COCO-pretrained checkpoint with no adaptation. "
            "It is **uninformative on the current primitives** (ADR-0004, amendment of "
            "2026-09-10): a rectangular box is not recognisable as a person, so the "
            "figure measures the geometry rather than the model. It is shown for the "
            "record, not as a baseline this model improved upon.\n"
        )

    vm = training.get("validation_metrics", {})
    return f"""# Model card — `{name}`

- **Version:** `{name}`
- **Base checkpoint:** `{training["base_checkpoint"]}`
- **Trained:** {training["trained_at"][:19].replace("T", " ")} UTC
- **Platform:** {training["platform"]}, {training["device"]}
- **Weights:** `{training["weights"]}`

## Purpose

Detect the four REWIND entity classes — `person`, `robot`, `forklift`, `pallet` — in
frames from the three fixed warehouse cameras. It is the first stage of the
perception pipeline; its boxes feed the tracker and everything downstream.

It is a **fine-tuned** model, not one trained from scratch: pretrained initialisation,
{training["epochs"]} epochs, {training["elapsed_s"]:.0f} seconds of compute (ADR-0004).

## Data

| | |
|---|---|
| Source | `{training["dataset"]}`, exported by `scripts/ml/export_yolo_dataset.py` |
| Training cases | {", ".join(f"`{c}`" for c in TRAIN_CASES)} |
| Validation case | `case_05`, the negative case |
| Held out entirely | `case_02`, `case_06` — golden, not opened until E9.1 |
| Frames | every 5th at 10 FPS, 1280x720, three cameras |
| Ground truth | ray-cast from the Blender scene, visible-box convention |

Validation uses the negative case deliberately: a model that memorised "the thing at
the intersection at 13 s" scores badly on it rather than well. Ground truth drops any
entity under 15% visible, so occlusion reads as a gap rather than a miss. Augmentation
is a training-time transform on frames and does not conflict with the scene spec's
constant-lighting rule, which fixes the rendered scene.

The training data is **entirely synthetic and entirely primitive**. Every entity is an
untextured box at its real-world footprint. No real footage, no real people.

## Training

| | |
|---|---|
| Epochs | {training["epochs"]} |
| Image size | {training["imgsz"]} |
| Batch | {training["batch"]} |
| Seed | {training["seed"]}, deterministic |
| Augmentation | HSV jitter, horizontal flip, mosaic |
| Val mAP50 | {vm.get("map50", float("nan")):.3f} |
| Val mAP50-95 | {vm.get("map", float("nan")):.3f} |

## Metrics

Evaluated on `{evaluation["case_id"]}` ({evaluation["frames_processed"]} frames) with
`scripts/evaluation/baseline_detection.py`, scored per class against ray-cast ground
truth at IoU 0.5.

| Class | Truth | Precision | Recall | F1 | Zero-shot recall |
|---|---|---|---|---|---|
{table}
{zero_shot_note}
{_golden_section(golden or [], post_golden)}## Limitations

**This model has only ever seen boxes.** It was trained and evaluated on untextured
primitives in a single synthetic scene under one lighting setup. Its scores say it can
separate four box shapes and colours from a grey floor. They say nothing about real
forklifts, real people, real lighting or real cameras, and the model should be assumed
to fail on all of them until the asset swap and the public-footage check (stretch
backlog) have been done.

**Train and test share one scene.** Every camera angle, every rack position and every
floor marking in the evaluation frames was also in the training frames. This mirrors a
fixed-camera facility deployment, which genuinely is fine-tuned per site, but it means
the numbers above are a ceiling for this scene rather than an estimate for any other.

**The validation case selected the checkpoint.** `best.pt` is the epoch with the
highest validation mAP, so `case_05` is not a fully independent test. The unbiased
number is the held-out section{"" if golden else ", once E9.1 has run"}.

**Class balance is uneven.** `forklift` and `pallet` appear in far fewer frames than
`person` and `robot`, because only one of the three training cases contains them.
Their scores rest on less evidence.{unmeasured_note}

{limitations}
## Provenance

Training record: `{pathlib.Path(training["weights"]).parent / "training.json"}`
Evaluation: `{evaluation.get("_source", "see benchmark-reports")}`
Held-out: {", ".join(f"`{g['_source']}`" for g in golden or []) or "not yet measured"}
"""


def main() -> int:
    """Generate the card for one promoted checkpoint."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--evaluation", type=pathlib.Path, required=True)
    parser.add_argument("--zero-shot", type=pathlib.Path, default=None)
    parser.add_argument("--golden", type=pathlib.Path, nargs="*", default=[])
    parser.add_argument(
        "--post-golden",
        default=None,
        help="the experiment record; marks the golden numbers as post-golden, not held-out",
    )
    args = parser.parse_args()

    training = json.loads((MODELS / args.name / "training.json").read_text())
    evaluation = json.loads(args.evaluation.read_text())
    evaluation["_source"] = str(args.evaluation)
    zero_shot = json.loads(args.zero_shot.read_text()) if args.zero_shot else None
    golden = [json.loads(path.read_text()) | {"_source": str(path)} for path in args.golden]
    limits = MODELS / args.name / "limitations.md"
    limitations = limits.read_text() if limits.exists() else ""

    CARDS.mkdir(parents=True, exist_ok=True)
    out = CARDS / f"{args.name}.md"
    out.write_text(render(training, evaluation, zero_shot, golden, limitations, args.post_golden))
    log.info("wrote %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
