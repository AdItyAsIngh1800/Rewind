# Design pass, 2026-09-15

A preserve-mode pass over the four screens, driven by screenshots at 1440 and 400 px
(agent-browser, Chrome) and two design skills' checklists. The PS-8 tokens, the
evidence-state encoding and the information architecture were the starting material
and are unchanged.

## What was audited

| Screen | 1440 px | 400 px |
|---|---|---|
| Case inbox | A bare table; no summary, no way to start a run, a filters-only empty state | Table scrolls in its container; header wrapped to two lines |
| Case workspace | Replay, three views, inspector; sound | Stacks correctly; three panes full width |
| System health | Tiles with dashes for unmeasured values; sound | Two columns |
| Analytics | Sound | Two columns |

The generated design system (`ui-ux-pro-max --design-system`, dense dashboard) proposed
an operational-green palette and a display face (Orbitron). Rejected: the project's
palette is a contrast-verified neutral with colour reserved for evidence state, and a
display face has no job on a screen of identifiers and timestamps. Kept from its
checklist: visible focus, live figures labelled with their update time and a stale
state (System Health already does), no hidden error states, 375–1440 px. From
taste-skill, which scopes itself out of dashboards: one accent, one radius scale, full
loading / empty / error cycles, a copy re-read.

## What changed

1. **Process footage from the browser.** `GET /sources` lists the case directories
   with their clip count and latest run; a native `<dialog>` on the inbox (investigators
   only) queues a run and reports whether it was created or already existed. Roadmap
   Part 6's verification begins "create a case, entirely through the browser", which
   needed `curl` until now.
2. **The inbox as a dashboard.** A strip of four tiles: open, high or critical,
   dismissed, runs in progress. Runs are polled every 3 s only while one is queued or
   running, and a completed run invalidates the case queries, so the incident row
   appears without a reload.
3. **Empty states that say what to do**: filtered / run in progress / no incidents, by
   role.
4. **Header on one line at phone width**: nowrap labels, the account name hidden
   below `sm`, the role kept.

## What was not changed, and why

- Cards on System Health and the inbox strip: elevation groups a number with its
  caveat, and the caveat is the point of those tiles.
- Middle dots in metadata lines (`0.1.0 · schema 1.2.0 · 45 ms`): one line of
  identifiers, not prose.
- `—` as the unmeasured placeholder: it is a value, not punctuation, and the tile's
  detail line says why it is unmeasured.
- Lucide icons: already the project's one icon family.

## Verified

Chrome, 1440 px: dialog opens with focus on the select, lists seven sources with
their latest run, queues `case_01` (`created: true`), the tile shows the run queued
then running, the row appears on completion (3 → 4 incidents) without a reload,
Escape closes. 400 px: header 42 px high on one line, no horizontal scroll.
