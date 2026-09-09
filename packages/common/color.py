"""Verify the interface colour tokens against WCAG contrast and colour-vision deficiency.

PS-8 fixes the evidence-state encoding, which is the single most important visual
decision in the product: an investigator must never mistake an inference for an
observation. The encoding therefore uses three independent channels — colour, pattern
and label — and this script proves the colour channel actually works rather than
assuming it does.

Two things are checked:

1. **Contrast.** Every foreground token against the surface it sits on, WCAG 2.1
   relative luminance, 4.5:1 for body text and 3:1 for large text and non-text marks.
2. **Distinguishability under colour-vision deficiency.** The five evidence states are
   simulated under protanopia, deuteranopia and tritanopia and their pairwise
   perceptual distance is measured in OKLab. Colour alone is never sufficient — the
   pattern and label channels carry the meaning — but two states collapsing into the
   same colour would still be a defect worth catching.

    make verify-contrast
"""

from __future__ import annotations

import math

# --------------------------------------------------------------------------
# Colour space conversions
# --------------------------------------------------------------------------

Rgb = tuple[float, float, float]


def srgb_to_linear(channel: float) -> float:
    """Undo the sRGB transfer function for one channel in 0..1."""
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def linear_to_srgb(channel: float) -> float:
    """Apply the sRGB transfer function to one linear channel in 0..1."""
    if channel <= 0.0031308:
        return 12.92 * channel
    return float(1.055 * (channel ** (1 / 2.4)) - 0.055)


def oklch_to_linear_rgb(lightness: float, chroma: float, hue_deg: float) -> Rgb:
    """Convert OKLCH to linear sRGB.

    Tokens are authored in OKLCH because that is what shadcn/ui and Tailwind v4
    expect, and because equal lightness steps in OKLCH look equal, which matters
    when five semantic states must read as siblings rather than a hierarchy.
    """
    hue = math.radians(hue_deg)
    a = chroma * math.cos(hue)
    b = chroma * math.sin(hue)

    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b

    long, med, short = l_**3, m_**3, s_**3

    return (
        4.0767416621 * long - 3.3077115913 * med + 0.2309699292 * short,
        -1.2684380046 * long + 2.6097574011 * med - 0.3413193965 * short,
        -0.0041960863 * long - 0.7034186147 * med + 1.7076147010 * short,
    )


def linear_rgb_to_oklab(rgb: Rgb) -> tuple[float, float, float]:
    """Convert linear sRGB to OKLab, for perceptual distance comparisons."""
    r, g, b = rgb
    long = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    med = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    short = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (max(v, 0.0) ** (1 / 3) for v in (long, med, short))
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def to_hex(rgb: Rgb) -> str:
    """Render a linear sRGB triple as a clamped hex string."""
    channels = [max(0, min(255, round(linear_to_srgb(max(0.0, min(1.0, c))) * 255))) for c in rgb]
    return "#{:02X}{:02X}{:02X}".format(*channels)


# --------------------------------------------------------------------------
# WCAG contrast
# --------------------------------------------------------------------------


def relative_luminance(rgb: Rgb) -> float:
    """WCAG 2.1 relative luminance from linear sRGB."""
    r, g, b = (max(0.0, min(1.0, c)) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: Rgb, b: Rgb) -> float:
    """Contrast ratio between two colours, always >= 1.0."""
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


# --------------------------------------------------------------------------
# Colour vision deficiency simulation
# --------------------------------------------------------------------------

#: Machado, Oliveira and Fernandes (2009), severity 1.0, applied in linear RGB.
CVD_MATRICES: dict[str, tuple[Rgb, Rgb, Rgb]] = {
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritanopia": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}


def simulate_cvd(rgb: Rgb, kind: str) -> Rgb:
    """Simulate how a colour appears under one form of dichromacy."""
    rows = CVD_MATRICES[kind]
    return tuple(sum(rows[i][j] * rgb[j] for j in range(3)) for i in range(3))  # type: ignore[return-value]


def perceptual_distance(a: Rgb, b: Rgb) -> float:
    """Euclidean distance between two colours in OKLab.

    Roughly, values below 0.10 read as "the same colour at a glance" for adjacent
    small marks such as a timeline segment or a graph edge.
    """
    la, aa, ba = linear_rgb_to_oklab(a)
    lb, ab, bb = linear_rgb_to_oklab(b)
    return math.sqrt((la - lb) ** 2 + (aa - ab) ** 2 + (ba - bb) ** 2)
