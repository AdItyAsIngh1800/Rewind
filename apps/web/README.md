# web

The investigator UI: React 19, TypeScript, Vite, Tailwind v4, shadcn/ui, TanStack Query.

    pnpm install
    make mock       # golden fixtures at :8000, or `make api` for the real thing
    make web        # :5173, proxies /api to :8000

`make web-build` is the gate CI runs: `tsc -b` then `vite build`.

## Rules that are not obvious from the code

- **Colour is reserved for evidence.** `src/styles/tokens.css` is generated from
  `scripts/maintenance/verify_contrast.py` and must not be edited by hand. Chrome is
  monochrome; severity is carried by weight (`SeverityMark`), never hue, so that a red
  chip can never be mistaken for conflicting evidence.
- **shadcn's colour names alias PS-8 tokens** in `globals.css`. Generated components
  therefore inherit the verified palette; do not introduce a second one.
- **`src/api/types.ts` mirrors `packages/schemas`.** The Pydantic contract is the
  authority; this file follows it and never leads.
- **Filters live in the URL.** A filtered inbox is a link a colleague can open.
- **Motion explains state, never decorates.** `--motion-fast`/`--motion-base` collapse to
  zero under `prefers-reduced-motion`. No global transitions.
- **A case page is one URL.** `view` (report, timeline, evidence) and `ref` (the
  selected evidence id) are search parameters, so "look at this node" is a link and
  back walks through what was inspected. Every view selects into the one inspector.
- **Evidence patterns are `ev-<level>` classes** in `globals.css`, the same gradients as
  `docs/ui/swatches.html`. Composed class names are invisible to Tailwind, hence plain CSS.
- **The graph layout is fixed, not force-directed:** a node sits in the same place every
  time a case opens. See the ledger row for E8.4.
- **`null` is "not measured", never zero.** Health tiles show a dash and say which phase
  measures the value. A zero would read as idle and healthy.
- **A status change refetches every case query**, so the inbox, a case and analytics
  never disagree about where an investigation stands.
- **The replay has one leading pane.** Its presented frames set the shared clock and the
  other panes are corrected only when they drift past a frame; clip time is shared time
  plus the camera's clock offset. Any selection with a moment seeks all three.
