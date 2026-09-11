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
