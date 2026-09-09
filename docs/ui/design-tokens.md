# UI — Design tokens

- **Decided:** PS-8, 2026-09-09
- **Source of truth:** `scripts/maintenance/verify_contrast.py`
- **Generated artefacts:** `apps/web/src/styles/tokens.css`, `docs/ui/swatches.html`
- **Verify:** `make verify-contrast` &middot; **Regenerate:** `make tokens`

The CSS and the swatch page are generated from the same Python source that the
verifier checks. Editing `tokens.css` by hand is therefore a mistake: the shipped
values would no longer be the verified values, and nothing would tell you.

---

## 1. What this is for

REWIND's entire claim is that a reader can tell an observation from an inference from
a gap. That distinction is carried visually. If the visual encoding fails, the claim
fails, regardless of how good the evidence graph is.

So the encoding is treated as engineering with a test, not as styling.

## 2. Three channels, always

Every evidence state is encoded on **colour, pattern and text label** simultaneously.

| State | Language | Pattern | Dark | Light |
|---|---|---|---|---|
| Confirmed | "Observed" | solid fill | `#65B5FF` | `#003F8C` |
| Strongly inferred | "Likely contributed" | dashed | `#4FDDDD` | `#003E40` |
| Possible | "Possible" | dotted | `#FFD656` | `#9C6700` |
| Conflicting | "Conflicting evidence" | cross-hatch | `#E14B39` | `#B31D1A` |
| Unknown | "Cannot determine" | diagonal hatch | `#999C9F` | `#4F5154` |

The wording is not decorative. It is the `ALLOWED_LANGUAGE` table from
`packages/schemas/enums.py`, and the report generator has no other vocabulary
available. The interface and the report therefore say the same words about the same
evidence, which is what makes a screenshot of the UI and a printed report agree.

## 3. Why lightness carries the encoding

The first palette attempt used five distinct hues and failed verification in four
places. The failures were instructive rather than cosmetic.

**A dichromat perceives roughly a two-dimensional colour space.** Five categories
cannot be reliably separated by hue for every form of colour-vision deficiency, and
tuning hues until a checker passes would be pretending otherwise.

So the palette is built on a **lightness ladder**: the five states occupy distinct
rungs with at least 0.05 OKLCH lightness between neighbours. Lightness separation
survives protanopia, deuteranopia, tritanopia, greyscale printing, a screenshot pasted
into a document, and a washed-out projector in a review meeting. Hue then adds
recognition speed for readers who can use it, and pattern adds a channel that survives
even total colour loss.

`docs/ui/swatches.html` includes a greyscale strip specifically to make this checkable
by eye rather than only by script.

### One deliberate asymmetry

Dark and light do not mirror each other's lightness ordering. Amber is intrinsically
light; forcing it onto the darkest rung in light mode turned it brown and it stopped
reading as caution at all. **Hue identity was kept and the ordering was allowed to
differ**, because a state that no longer looks like itself has lost more than a state
whose relative prominence shifts between themes.

## 4. Colour is reserved for evidence

The interface chrome is monochrome. There is no brand accent competing with the
semantic palette, and the focus ring is a **neutral**, never a semantic colour: a
focus ring in amber would read as "possible" to anyone scanning the encoding.

Interactive affordance is carried by weight, border and position instead of hue. In a
tool whose only job is to communicate evidence strength, spending colour on a button
would be spending it in the wrong place.

## 5. Typography

| Role | Face | Why |
|---|---|---|
| Interface | **Fira Sans** | Matched by the UI database for "dashboards, analytics, data visualisation, admin panels". Avoids Inter, the discouraged default |
| Data | **Fira Mono** | Timestamps, evidence ids, camera ids, confidence values |

Fira Mono rather than Fira Code deliberately: programming ligatures belong in an
editor, not in a timestamp column where `10:32:10` must read as digits.

Tabular numerals are mandatory anywhere digits stack vertically. Without them a
timeline column visibly jitters between frames, which reads as instability in a tool
whose credibility depends on looking precise.

## 6. Scales

**Type** runs 11px to 26px. A narrow range on purpose: this is an instrument, and
hierarchy comes from weight and colour rather than from size jumps. 26px is the
largest thing on any screen.

**Spacing** is tight (4px to 32px). The density target is high because an investigator
needs three video panes, the timeline and the evidence graph visible at once.

**Radius** is one system: 2px for chips and markers, 4px for inputs and buttons, 6px
for panels. Small values keep the read technical.

## 7. Motion

`--motion-fast: 120ms`, `--motion-base: 180ms`, and both collapse to `0ms` under
`prefers-reduced-motion`.

Transitions exist only to explain a state change: a timeline seek, a graph node
expanding, a panel opening. An investigator tool should feel instant. Nothing on this
interface animates to attract attention, because everything that needs attention is
already evidence.

## 8. Theme policy

Dark is primary: this interface is read for long sessions. Light exists because
reports get printed and reviewed in daylight, and because a mentor or examiner will
open it on a projector.

Both themes are fully specified. `tokens.css` defines the complete light palette on
bare `:root`, redefines only the changed tokens under `prefers-color-scheme: dark`
guarded as `:root:not([data-theme="light"])`, and again under `:root[data-theme="dark"]`
so an explicit toggle wins in both directions.

## 9. What is verified, and what is not

`make verify-contrast` checks, and fails the build on:

- WCAG 2.1 contrast for every text token and every evidence state against its ground
  (4.5:1 body, 3:1 marks)
- The lightness ladder: at least 0.05 separation between adjacent rungs
- Pairwise separation of all five states under protanopia, deuteranopia and tritanopia

It does **not** check the pattern channel, which is CSS, or the label channel, which is
content. Those are verified by eye on `swatches.html` and by the `ALLOWED_LANGUAGE`
contract test in `tests/unit/test_schemas.py`.

## 10. Consumed by

E8.1 imports `tokens.css` and maps it into Tailwind v4 through the `@theme inline`
block already present in the file. Components reference semantic names only
(`--color-confirmed`), never a raw palette value, so a token change propagates
everywhere at once.
