"""Emit the evidence-encoding swatch page.

A static page showing all five evidence states in both themes, with their patterns,
labels, hex values and measured contrast ratios. Everything on it is computed from
the verified tokens, so the numbers printed on the page are the numbers that were
checked.

Its real job is the greyscale strip near the bottom. Colour is the channel most
likely to be lost - to a projector, a printer, a screenshot, or a reader's eyes - and
the greyscale strip is the proof that the encoding survives losing it.

    make tokens
"""

from __future__ import annotations

import logging
import pathlib

from packages.common.color import contrast_ratio, oklch_to_linear_rgb, to_hex
from scripts.maintenance.verify_contrast import (
    DARK,
    EVIDENCE_DARK,
    EVIDENCE_LIGHT,
    LIGHT,
)
from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

OUT = pathlib.Path("docs/ui/swatches.html")

#: The pattern channel. Each evidence state carries a distinct fill so the encoding
#: survives greyscale, colour-vision deficiency and a washed-out projector.
PATTERNS: dict[str, tuple[str, str]] = {
    "confirmed": ("solid fill", "background: var(--c);"),
    "inferred": (
        "dashed",
        "background: repeating-linear-gradient(90deg, var(--c) 0 10px, transparent 10px 17px);",
    ),
    "possible": (
        "dotted",
        "background: repeating-linear-gradient(90deg, var(--c) 0 3px, transparent 3px 9px);",
    ),
    "conflicting": (
        "cross-hatch",
        "background: repeating-linear-gradient(45deg, var(--c) 0 2px, transparent 2px 7px),"
        " repeating-linear-gradient(-45deg, var(--c) 0 2px, transparent 2px 7px);",
    ),
    "unknown": (
        "diagonal hatch",
        "background: repeating-linear-gradient(45deg, var(--c) 0 2px, transparent 2px 8px);",
    ),
}

LANGUAGE: dict[str, str] = {
    "confirmed": "Observed",
    "inferred": "Likely contributed",
    "possible": "Possible",
    "conflicting": "Conflicting evidence",
    "unknown": "Cannot determine",
}

ORDER = ["confirmed", "inferred", "possible", "conflicting", "unknown"]


def rows(
    evidence: dict[str, tuple[float, float, float]], ground: tuple[float, float, float]
) -> str:
    """Render the swatch rows for one theme."""
    ground_rgb = oklch_to_linear_rgb(*ground)
    out = []
    for key in ORDER:
        token = evidence[key]
        rgb = oklch_to_linear_rgb(*token)
        ratio = contrast_ratio(rgb, ground_rgb)
        pattern_name, pattern_css = PATTERNS[key]
        out.append(f"""    <div class="state">
      <div class="chip" style="--c: var(--evidence-{key}); {pattern_css}"></div>
      <div class="meta">
        <div class="name">{key}</div>
        <div class="say">&ldquo;{LANGUAGE[key]}&rdquo;</div>
        <div class="mono">{to_hex(rgb)} &middot; {ratio:.2f}:1 &middot; L {token[0]:.3f}</div>
        <div class="pat">{pattern_name}</div>
      </div>
    </div>""")
    return "\n".join(out)


def inline_theme(
    palette: dict[str, tuple[float, float, float]], evidence: dict[str, tuple[float, float, float]]
) -> str:
    """Render a theme as inline custom properties.

    The token selectors in tokens.css are :root-scoped, which is correct for the real
    application but means a nested element cannot switch themes. This page needs both
    themes visible at once, so the light panel carries its own properties inline.
    """
    parts = [f"--{name}: {oklch_css(v)}" for name, v in palette.items()]
    parts += [f"--evidence-{name}: {oklch_css(v)}" for name, v in evidence.items()]
    parts += ["background: var(--surface)", "color: var(--text)"]
    return "; ".join(parts) + ";"


def oklch_css(value: tuple[float, float, float]) -> str:
    """Render a token triple as a CSS oklch() function."""
    lightness, chroma, hue = value
    return f"oklch({lightness:.3f} {chroma:.3f} {hue:g})"


def main() -> int:
    """Write the swatch page."""
    html = f"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>REWIND evidence encoding</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fira+Sans:wght@400;500;600&family=Fira+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="../../apps/web/src/styles/tokens.css">
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: var(--space-6);
    background: var(--ground); color: var(--text);
    font-family: var(--font-ui); font-size: var(--text-base); line-height: 1.55;
  }}
  h1 {{ font-size: var(--text-xl); font-weight: 600; margin: 0 0 var(--space-2); }}
  h2 {{ font-size: var(--text-lg); font-weight: 600; margin: var(--space-6) 0 var(--space-3); }}
  p  {{ max-width: 68ch; color: var(--text-muted); margin: 0 0 var(--space-3); }}
  .mono {{ font-family: var(--font-mono); font-variant-numeric: tabular-nums;
           font-size: var(--text-xs); color: var(--text-dim); }}
  .panel {{ background: var(--surface); border: 1px solid var(--border);
            border-radius: var(--radius-lg); padding: var(--space-5);
            margin-bottom: var(--space-5); }}
  .states {{ display: grid; gap: var(--space-4);
             grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }}
  .chip {{ height: 40px; border: 1.5px solid var(--c); border-radius: var(--radius-sm); }}
  .name {{ font-weight: 600; margin-top: var(--space-2); text-transform: capitalize; }}
  .say {{ color: var(--text-muted); font-size: var(--text-sm); }}
  .pat {{ font-size: var(--text-2xs); text-transform: uppercase; letter-spacing: .1em;
          color: var(--text-dim); margin-top: var(--space-1); }}
  .grey {{ filter: grayscale(1); }}
  .ladder {{ display: grid; gap: 2px; grid-template-columns: repeat(5, 1fr); }}
  .rung {{ height: 56px; display: flex; align-items: flex-end; padding: var(--space-1);
           font-family: var(--font-mono); font-size: var(--text-2xs); color: #fff;
           mix-blend-mode: normal; }}
  .swatchrow {{ display: grid; gap: var(--space-2);
                grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); }}
  .tok {{ border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; }}
  .tok .fill {{ height: 34px; }}
  .tok .lbl {{ padding: var(--space-2); font-family: var(--font-mono);
               font-size: var(--text-2xs); }}
  .note {{ border-left: 3px solid var(--evidence-possible); padding-left: var(--space-4);
           color: var(--text-muted); }}
</style>
</head>
<body>

<h1>Evidence encoding</h1>
<p class="mono">GENERATED &middot; make tokens &middot; verified by make verify-contrast</p>
<p>Five evidence states, each encoded on <strong>three independent channels</strong>: colour,
pattern and text label. An investigator must never mistake an inference for an observation,
and colour alone cannot carry that distinction reliably.</p>

<div class="panel">
  <h2 style="margin-top:0">Dark theme</h2>
  <div class="states">
{rows(EVIDENCE_DARK, DARK["ground"])}
  </div>
</div>

<div class="panel" style="{inline_theme(LIGHT, EVIDENCE_LIGHT)}">
  <h2 style="margin-top:0">Light theme</h2>
  <div class="states">
{rows(EVIDENCE_LIGHT, LIGHT["ground"])}
  </div>
</div>

<div class="panel">
  <h2 style="margin-top:0">The greyscale test</h2>
  <p class="note">This is the proof that matters. Colour is the channel most likely to be
  lost, to a projector, a printer, a screenshot or a reader&rsquo;s eyes. Below, the same five
  states with all colour removed. They remain distinguishable because they sit on separate
  rungs of a lightness ladder and because the pattern channel is doing real work.</p>
  <div class="states grey">
{rows(EVIDENCE_DARK, DARK["ground"])}
  </div>
</div>

<div class="panel">
  <h2 style="margin-top:0">Lightness ladder</h2>
  <p>Dark theme, ordered by OKLCH lightness. Separation of at least 0.05 between adjacent
  rungs is what survives every form of colour-vision deficiency.</p>
  <div class="ladder">
{
        chr(10).join(
            f'    <div class="rung" style="background: var(--evidence-{k})">L {DARK_L:.3f}</div>'
            for k, DARK_L in [
                (k, EVIDENCE_DARK[k][0])
                for k in sorted(EVIDENCE_DARK, key=lambda x: EVIDENCE_DARK[x][0])
            ]
        )
    }
  </div>
</div>

<div class="panel">
  <h2 style="margin-top:0">Surface and text tokens</h2>
  <div class="swatchrow">
{
        chr(10).join(
            f'    <div class="tok"><div class="fill" style="background: var(--{n})"></div>'
            f'<div class="lbl">--{n}<br>{to_hex(oklch_to_linear_rgb(*v))}</div></div>'
            for n, v in DARK.items()
        )
    }
  </div>
</div>

<div class="panel">
  <h2 style="margin-top:0">Type scale</h2>
  <div style="font-size: var(--text-2xs)">2xs &middot; 11px &middot; uppercase micro-labels</div>
  <div style="font-size: var(--text-xs)">xs &middot; 12px &middot; table meta and timestamps</div>
  <div style="font-size: var(--text-sm)">sm &middot; 13px &middot; dense table body</div>
  <div style="font-size: var(--text-base)">base &middot; 14px &middot; default UI body</div>
  <div style="font-size: var(--text-md)">md &middot; 16px &middot; report reading text</div>
  <div style="font-size: var(--text-lg)">lg &middot; 20px &middot; panel titles</div>
  <div style="font-size: var(--text-xl)">xl &middot; 26px &middot; largest on any screen</div>
  <p class="mono" style="margin-top: var(--space-3)">
    10:32:10.400 &middot; CAM_A &middot; OBS-0003 &middot; 0.94 &nbsp;&larr; Fira Mono, tabular
  </p>
</div>

</body>
</html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    log.info(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    configure_logging()
    raise SystemExit(main())
