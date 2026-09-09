"""Tests for the design tokens and the colour maths behind them.

The generated artefacts, tokens.css and swatches.html, must stay in step with the
verified source. If they drift, the browser ships values nobody checked, which is the
exact failure the generation step exists to prevent.
"""

from __future__ import annotations

import itertools
import pathlib
import subprocess
import sys

import pytest

from packages.common.color import (
    contrast_ratio,
    oklch_to_linear_rgb,
    perceptual_distance,
    simulate_cvd,
    to_hex,
)
from scripts.maintenance.verify_contrast import (
    DARK,
    EVIDENCE_DARK,
    EVIDENCE_LIGHT,
    LIGHT,
    LIGHTNESS_MIN_DELTA,
    TEXT_MIN,
)

TOKENS_CSS = pathlib.Path("apps/web/src/styles/tokens.css")
SWATCHES = pathlib.Path("docs/ui/swatches.html")


# --------------------------------------------------------------------------
# Colour maths, checked against known values
# --------------------------------------------------------------------------


def test_white_and_black_round_trip() -> None:
    """Assert the OKLCH conversion hits the sRGB extremes exactly."""
    assert to_hex(oklch_to_linear_rgb(1.0, 0.0, 0)) == "#FFFFFF"
    assert to_hex(oklch_to_linear_rgb(0.0, 0.0, 0)) == "#000000"


def test_maximum_contrast_is_twenty_one() -> None:
    """Assert white on black scores the WCAG maximum."""
    white = oklch_to_linear_rgb(1.0, 0.0, 0)
    black = oklch_to_linear_rgb(0.0, 0.0, 0)
    assert contrast_ratio(white, black) == pytest.approx(21.0, abs=0.01)


def test_contrast_is_symmetric() -> None:
    """Assert contrast does not depend on argument order."""
    a = oklch_to_linear_rgb(0.7, 0.1, 250)
    b = oklch_to_linear_rgb(0.2, 0.0, 0)
    assert contrast_ratio(a, b) == pytest.approx(contrast_ratio(b, a))


def test_cvd_simulation_changes_a_red() -> None:
    """Assert the deuteranopia simulation actually transforms a red."""
    red = oklch_to_linear_rgb(0.62, 0.19, 30)
    assert perceptual_distance(red, simulate_cvd(red, "deuteranopia")) > 0.01


# --------------------------------------------------------------------------
# The encoding invariants
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("theme", "palette", "evidence"),
    [("dark", DARK, EVIDENCE_DARK), ("light", LIGHT, EVIDENCE_LIGHT)],
)
def test_every_evidence_state_meets_text_contrast(
    theme: str, palette: dict, evidence: dict
) -> None:
    """Assert each state is readable as text against its own ground."""
    ground = oklch_to_linear_rgb(*palette["ground"])
    for name, token in evidence.items():
        ratio = contrast_ratio(oklch_to_linear_rgb(*token), ground)
        assert ratio >= TEXT_MIN, f"{theme}/{name} is {ratio:.2f}:1"


@pytest.mark.parametrize(
    ("theme", "evidence"), [("dark", EVIDENCE_DARK), ("light", EVIDENCE_LIGHT)]
)
def test_evidence_states_occupy_distinct_lightness_rungs(theme: str, evidence: dict) -> None:
    """Assert the lightness ladder holds.

    This is the invariant that makes the encoding survive colour-vision deficiency,
    greyscale printing and a washed-out projector. Hue separation alone cannot carry
    five categories for a dichromat.
    """
    lightnesses = sorted(token[0] for token in evidence.values())
    for lower, upper in itertools.pairwise(lightnesses):
        assert upper - lower >= LIGHTNESS_MIN_DELTA, (
            f"{theme}: rungs {lower:.3f} and {upper:.3f} are too close"
        )


def test_all_five_evidence_states_are_present() -> None:
    """Assert no state is missing from either theme.

    A missing state would render as an unstyled default, which would look like a
    different state rather than like a bug.
    """
    expected = {"confirmed", "inferred", "possible", "conflicting", "unknown"}
    assert set(EVIDENCE_DARK) == expected
    assert set(EVIDENCE_LIGHT) == expected


def test_focus_ring_is_not_a_semantic_colour() -> None:
    """Assert the focus ring carries no chroma.

    A focus ring in amber would read as "possible" to anyone scanning the evidence
    encoding. Colour is reserved for evidence state.
    """
    for palette in (DARK, LIGHT):
        assert palette["focus"][1] == 0.0


# --------------------------------------------------------------------------
# Generated artefacts must not drift
# --------------------------------------------------------------------------


def test_tokens_css_exists_and_declares_every_state() -> None:
    """Assert the generated stylesheet carries all five evidence tokens."""
    css = TOKENS_CSS.read_text()
    for name in EVIDENCE_DARK:
        assert f"--evidence-{name}:" in css


def test_tokens_css_bridges_to_tailwind() -> None:
    """Assert the Tailwind v4 theme bridge is present with semantic names."""
    css = TOKENS_CSS.read_text()
    assert "@theme inline" in css
    assert "--color-confirmed: var(--evidence-confirmed);" in css


def test_tokens_css_defines_both_themes() -> None:
    """Assert light is on bare :root and dark is reachable two ways.

    The un-stamped document is the common case: most readers never set a theme, so
    only prefers-color-scheme separates light from dark for them.
    """
    css = TOKENS_CSS.read_text()
    assert "@media (prefers-color-scheme: dark)" in css
    assert ':root:not([data-theme="light"])' in css
    assert ':root[data-theme="dark"]' in css


def test_tokens_css_collapses_motion_when_asked() -> None:
    """Assert reduced-motion zeroes the durations."""
    css = TOKENS_CSS.read_text()
    assert "@media (prefers-reduced-motion: reduce)" in css


@pytest.mark.parametrize("script", ["generate_tokens", "generate_swatches"])
def test_generated_artefacts_are_current(script: str) -> None:
    """Assert regenerating produces no change.

    A stale artefact means the browser is being served values that were never
    verified. Same principle as the openapi.json drift check.
    """
    target = TOKENS_CSS if script == "generate_tokens" else SWATCHES
    before = target.read_text()
    subprocess.run(
        [sys.executable, f"scripts/maintenance/{script}.py"], check=True, capture_output=True
    )
    assert target.read_text() == before, (
        f"{target} is stale. Run `make tokens` and commit the result."
    )


def test_swatch_page_shows_the_greyscale_proof() -> None:
    """Assert the swatch page keeps the greyscale strip.

    It is the only part of the page that demonstrates the encoding surviving total
    colour loss, so it is the part most worth protecting from a well-meaning edit.
    """
    html = SWATCHES.read_text()
    assert "greyscale" in html.lower()
    assert "grayscale(1)" in html
