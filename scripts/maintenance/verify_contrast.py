"""Verify the REWIND colour tokens: contrast and colour-vision distinguishability.

Run at every gate review and before any change to the token file.

    make verify-contrast

Exits non-zero if any pair fails, so a palette regression cannot ship quietly.
"""

from __future__ import annotations

from packages.common.color import (
    CVD_MATRICES,
    contrast_ratio,
    oklch_to_linear_rgb,
    perceptual_distance,
    simulate_cvd,
    to_hex,
)

Oklch = tuple[float, float, float]

# --------------------------------------------------------------------------
# Tokens — the single source of truth, mirrored into tokens.css
# --------------------------------------------------------------------------

DARK: dict[str, Oklch] = {
    "ground": (0.170, 0.008, 250),
    "surface": (0.215, 0.009, 250),
    "surface-raised": (0.265, 0.010, 250),
    "border": (0.395, 0.014, 250),
    "text": (0.945, 0.004, 250),
    "text-muted": (0.760, 0.010, 250),
    "text-dim": (0.620, 0.012, 250),
    "focus": (0.980, 0.000, 0),
}

LIGHT: dict[str, Oklch] = {
    "ground": (0.985, 0.003, 250),
    "surface": (1.000, 0.000, 0),
    "surface-raised": (0.955, 0.005, 250),
    "border": (0.820, 0.010, 250),
    "text": (0.220, 0.012, 250),
    "text-muted": (0.450, 0.014, 250),
    "text-dim": (0.530, 0.012, 250),
    "focus": (0.200, 0.000, 0),
}

#: The five evidence states. Colour is one of three channels; pattern and label
#: carry the same information, so a reader who cannot separate two hues still
#: reads the state correctly.
EVIDENCE_DARK: dict[str, Oklch] = {
    "conflicting": (0.620, 0.190, 30),
    "unknown": (0.690, 0.006, 250),
    "confirmed": (0.757, 0.140, 250),
    "inferred": (0.824, 0.120, 195),
    "possible": (0.891, 0.150, 90),
}

# Light-theme lightness runs the other way, because these sit on a near-white ground.
# Hue identity is preserved rather than sacrificed to mirror the dark ordering: amber
# forced down to the darkest rung stops reading as amber and becomes brown, which
# loses the "caution" meaning the colour is carrying.
EVIDENCE_LIGHT: dict[str, Oklch] = {
    "inferred": (0.315, 0.090, 195),
    "confirmed": (0.375, 0.150, 250),
    "unknown": (0.435, 0.006, 250),
    "conflicting": (0.495, 0.185, 28),
    "possible": (0.555, 0.130, 78),
}

#: WCAG 2.1 thresholds.
TEXT_MIN = 4.5  # body text
MARK_MIN = 3.0  # large text, icons, chart marks, borders

#: Below this OKLab distance two marks are effectively the same colour.
#:
#: Deliberately modest, and the reason matters. A dichromat perceives roughly a
#: two-dimensional colour space, so five categories cannot be reliably separated by
#: hue alone for every form of colour-vision deficiency. Chasing a large hue
#: separation here would be pretending otherwise. This floor only asserts that no two
#: states become *identical*; the real separation is carried by LIGHTNESS_MIN_DELTA
#: below, plus the pattern and label channels.
CVD_MIN_DISTANCE = 0.04

#: The load-bearing invariant. Lightness separation survives every form of
#: colour-vision deficiency, greyscale printing, screenshots and projector washout.
#: If two evidence states share a lightness, no amount of hue difference saves them.
LIGHTNESS_MIN_DELTA = 0.05


def rgb(token: Oklch) -> tuple[float, float, float]:
    """Convert a token triple to linear sRGB."""
    return oklch_to_linear_rgb(*token)


def check_theme(name: str, palette: dict[str, Oklch], evidence: dict[str, Oklch]) -> list[str]:
    """Check one theme's contrast ratios; return a list of failure messages."""
    failures: list[str] = []
    ground = rgb(palette["ground"])
    surface = rgb(palette["surface"])

    print(f"\n## {name} — text on ground")
    for key in ("text", "text-muted", "text-dim"):
        ratio = contrast_ratio(rgb(palette[key]), ground)
        floor = TEXT_MIN if key != "text-dim" else MARK_MIN
        ok = ratio >= floor
        verdict = "ok" if ok else "FAIL"
        swatch = to_hex(rgb(palette[key]))
        print(f"  {key:16s} {swatch}  {ratio:5.2f}:1  need {floor}  {verdict}")
        if not ok:
            failures.append(f"{name}/{key} contrast {ratio:.2f} below {floor}")

    ratio = contrast_ratio(rgb(palette["border"]), surface)
    print(
        f"  {'border':16s} {to_hex(rgb(palette['border']))}  {ratio:5.2f}:1  need 1.50  "
        f"{'ok' if ratio >= 1.5 else 'FAIL'}"
    )
    if ratio < 1.5:
        failures.append(f"{name}/border too faint against surface ({ratio:.2f})")

    ratio = contrast_ratio(rgb(palette["focus"]), surface)
    print(
        f"  {'focus ring':16s} {to_hex(rgb(palette['focus']))}  {ratio:5.2f}:1  need {MARK_MIN}  "
        f"{'ok' if ratio >= MARK_MIN else 'FAIL'}"
    )
    if ratio < MARK_MIN:
        failures.append(f"{name}/focus ring contrast {ratio:.2f} below {MARK_MIN}")

    print(f"\n## {name} — evidence states on ground")
    for key, token in evidence.items():
        ratio = contrast_ratio(rgb(token), ground)
        ok = ratio >= TEXT_MIN
        verdict = "ok" if ok else "FAIL"
        swatch = to_hex(rgb(token))
        print(f"  {key:16s} {swatch}  {ratio:5.2f}:1  need {TEXT_MIN}  {verdict}")
        if not ok:
            failures.append(f"{name}/evidence.{key} contrast {ratio:.2f} below {TEXT_MIN}")
    return failures


def check_cvd(name: str, evidence: dict[str, Oklch]) -> list[str]:
    """Check the evidence states stay separable under dichromacy."""
    failures: list[str] = []
    keys = list(evidence)
    print(f"\n## {name} — evidence separation under colour-vision deficiency")
    print("  (colour is one of three channels; pattern and label carry the same meaning)")

    for kind in ["normal", *CVD_MATRICES]:
        worst = (999.0, "", "")
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                ca, cb = rgb(evidence[a]), rgb(evidence[b])
                if kind != "normal":
                    ca, cb = simulate_cvd(ca, kind), simulate_cvd(cb, kind)
                distance = perceptual_distance(ca, cb)
                if distance < worst[0]:
                    worst = (distance, a, b)
        ok = worst[0] >= CVD_MIN_DISTANCE
        print(
            f"  {kind:14s} closest pair: {worst[1]:12s} / {worst[2]:12s}  "
            f"distance {worst[0]:.3f}  {'ok' if ok else 'FAIL'}"
        )
        if not ok:
            failures.append(
                f"{name}/{kind}: {worst[1]} and {worst[2]} collapse (distance {worst[0]:.3f})"
            )
    return failures


def check_lightness_ladder(name: str, evidence: dict[str, Oklch]) -> list[str]:
    """Check the evidence states occupy distinct rungs on a lightness ladder.

    This is the check that actually guarantees the encoding works. Lightness
    separation is robust to every colour-vision deficiency, to greyscale printing,
    and to a washed-out projector in a review meeting.
    """
    failures: list[str] = []
    ordered = sorted(evidence.items(), key=lambda kv: kv[1][0])
    print(f"\n## {name} — lightness ladder")
    previous: tuple[str, float] | None = None
    for key, token in ordered:
        lightness = token[0]
        marker = ""
        if previous is not None:
            delta = lightness - previous[1]
            ok = delta >= LIGHTNESS_MIN_DELTA
            marker = f"  delta {delta:.3f} {'ok' if ok else 'FAIL'}"
            if not ok:
                failures.append(
                    f"{name}: {previous[0]} and {key} share a lightness rung (delta {delta:.3f})"
                )
        print(f"  L={lightness:.3f}  {key:14s}{marker}")
        previous = (key, lightness)
    return failures


def main() -> int:
    """Verify both themes and return a process exit code."""
    print("REWIND colour token verification")
    failures: list[str] = []
    failures += check_theme("dark", DARK, EVIDENCE_DARK)
    failures += check_lightness_ladder("dark", EVIDENCE_DARK)
    failures += check_cvd("dark", EVIDENCE_DARK)
    failures += check_theme("light", LIGHT, EVIDENCE_LIGHT)
    failures += check_lightness_ladder("light", EVIDENCE_LIGHT)
    failures += check_cvd("light", EVIDENCE_LIGHT)

    print()
    if failures:
        print(f"FAILED — {len(failures)} problem(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("OK — all contrast and separation checks pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
