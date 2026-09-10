"""Emit tokens.css from the verified colour tokens.

The CSS is generated rather than hand-written so that the values shipped to the
browser and the values checked by ``verify_contrast.py`` cannot drift apart. Editing
tokens.css by hand is therefore a mistake: change the tokens in the verifier, re-run
it, and regenerate.

    make tokens
"""

from __future__ import annotations

import logging
import pathlib

from scripts.maintenance.verify_contrast import (
    DARK,
    EVIDENCE_DARK,
    EVIDENCE_LIGHT,
    LIGHT,
)
from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

OUT = pathlib.Path("apps/web/src/styles/tokens.css")

#: Type scale. Modest range on purpose: this is an instrument, not a landing page,
#: and hierarchy comes from weight and colour rather than from size jumps.
TYPE_SCALE = [
    ("--text-2xs", "0.6875rem", "11px, uppercase micro-labels only"),
    ("--text-xs", "0.75rem", "12px, table meta and timestamps"),
    ("--text-sm", "0.8125rem", "13px, dense table body"),
    ("--text-base", "0.875rem", "14px, default UI body"),
    ("--text-md", "1rem", "16px, reading text in the report view"),
    ("--text-lg", "1.25rem", "20px, panel titles"),
    ("--text-xl", "1.625rem", "26px, the largest thing on any screen"),
]

#: Spacing. Tight, because the density dial for this product is high: an investigator
#: needs the timeline, three video panes and the evidence graph on one screen.
SPACE_SCALE = [
    ("--space-1", "0.25rem"),
    ("--space-2", "0.5rem"),
    ("--space-3", "0.75rem"),
    ("--space-4", "1rem"),
    ("--space-5", "1.5rem"),
    ("--space-6", "2rem"),
]

#: One radius system, applied everywhere. Small values keep the read technical.
RADIUS_SCALE = [
    ("--radius-sm", "2px", "chips, badges, evidence markers"),
    ("--radius-md", "4px", "inputs, buttons, cards"),
    ("--radius-lg", "6px", "panels, dialogs"),
]


def oklch(value: tuple[float, float, float]) -> str:
    """Format one token triple for CSS."""
    lightness, chroma, hue = value
    return f"oklch({lightness:.3f} {chroma:.3f} {hue:g})"


def block(
    palette: dict[str, tuple[float, float, float]],
    evidence: dict[str, tuple[float, float, float]],
    indent: str = "  ",
) -> str:
    """Render one theme's custom properties."""
    lines = [f"{indent}--{name}: {oklch(v)};" for name, v in palette.items()]
    lines.append("")
    for name, v in evidence.items():
        lines.append(f"{indent}--evidence-{name}: {oklch(v)};")
    return "\n".join(lines)


def main() -> int:
    """Write tokens.css and report where it went."""
    css = f"""/* REWIND design tokens — GENERATED, do not edit by hand.
 *
 * Source of truth: scripts/maintenance/verify_contrast.py
 * Regenerate:      make tokens
 * Verify:          make verify-contrast
 *
 * Every colour below has been checked for WCAG contrast against its ground and for
 * separation under protanopia, deuteranopia and tritanopia. The five evidence states
 * additionally occupy distinct rungs of a lightness ladder, which is what makes them
 * legible in greyscale, in print and on a washed-out projector.
 *
 * COLOUR IS NEVER THE ONLY CHANNEL. Every evidence state also carries a pattern and
 * a text label. A dichromat perceives roughly a two-dimensional colour space, so five
 * categories cannot be separated by hue alone, and pretending otherwise would be the
 * accessibility failure this whole token system exists to avoid.
 */

:root {{
  color-scheme: light dark;

{block(LIGHT, EVIDENCE_LIGHT)}

  /* Typography. Fira Sans for the interface, Fira Mono for anything a reader might
   * compare digit by digit: timestamps, evidence ids, camera ids, confidence values.
   * Mono is chosen over Fira Code deliberately - programming ligatures belong in an
   * editor, not in a timestamp column. */
  --font-ui: "Fira Sans", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: "Fira Mono", ui-monospace, "SF Mono", Menlo, monospace;

{chr(10).join(f"  {n}: {v};  /* {note} */" for n, v, note in TYPE_SCALE)}

{chr(10).join(f"  {n}: {v};" for n, v in SPACE_SCALE)}

{chr(10).join(f"  {n}: {v};  /* {note} */" for n, v, note in RADIUS_SCALE)}

  /* Motion. An investigator tool should feel instant. Transitions exist only to
   * explain a state change, never to decorate one. */
  --motion-fast: 120ms;
  --motion-base: 180ms;
  --motion-ease: cubic-bezier(0.2, 0, 0, 1);
}}

/* Dark is the primary theme: this interface is read for long sessions in operations
 * rooms. Light exists because reports get printed and reviewed in daylight. */
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
{block(DARK, EVIDENCE_DARK, indent="    ")}
  }}
}}

:root[data-theme="dark"] {{
{block(DARK, EVIDENCE_DARK, indent="    ")}
}}

@media (prefers-reduced-motion: reduce) {{
  :root {{
    --motion-fast: 0ms;
    --motion-base: 0ms;
  }}
}}

/* Tailwind v4 bridge. Semantic names only - components never reference a raw
 * palette value, so a token change propagates everywhere at once. */
@theme inline {{
  --color-ground: var(--ground);
  --color-surface: var(--surface);
  --color-surface-raised: var(--surface-raised);
  --color-border: var(--border);
  --color-text: var(--text);
  --color-text-muted: var(--text-muted);
  --color-text-dim: var(--text-dim);
  --color-focus: var(--focus);

  --color-confirmed: var(--evidence-confirmed);
  --color-inferred: var(--evidence-inferred);
  --color-possible: var(--evidence-possible);
  --color-conflicting: var(--evidence-conflicting);
  --color-unknown: var(--evidence-unknown);

  --font-sans: var(--font-ui);
  --font-mono: var(--font-mono);
}}

/* Digits that stack in a column must not jitter between frames. */
.tabular {{
  font-variant-numeric: tabular-nums;
  font-family: var(--font-mono);
}}

/* Focus is a neutral, never a semantic colour: a focus ring in amber would read as
 * "possible" to anyone scanning the evidence encoding. */
:focus-visible {{
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}}
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(css)
    log.info(f"wrote {OUT} ({len(css.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    configure_logging()
    raise SystemExit(main())
