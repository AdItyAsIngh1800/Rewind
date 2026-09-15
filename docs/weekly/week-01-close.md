# Close-out — 2026-09-15

The roadmap is in weeks; the build ran 2026-09-09 to 2026-09-15. This is the one
closing log in place of the weekly series, and the audit
(`docs/audit/final-audit.md`) says why there is only `week-00` before it.

## Objectives set at the start

Everything in `ROADMAP.md` Parts 1 and 2, in order, with the reasoning layer's
schedule protected above all.

## Completed

PS-1–PS-9; E1–E11; Gates 1–7 reviewed; final audit and postmortem written. Owed items
are listed in `docs/14-future-work.md` §1.

## Benchmark movement

| Metric | Tune (gates) | Held-out (EXP-0010) | Post-golden (EXP-0011) | Explained by |
|---|---|---|---|---|
| Person recall | 0.994 | 0.065 | 0.065 | F2, accepted |
| False-link rate | 0.00 | 0.25 | 0.29 | F4, partial |
| Evidence coverage / unsupported | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | structural |
| Gap recall | — | ≥ 0.995 | ≥ 0.995 | F6 |

Every movement has an experiment record.

## Failures and what they cost

`docs/incidents/2026-09-14-golden-perception.md`; the frozen-actor render (−1.5 d,
repaid); the worker speed misreport (corrected same day).

## Decisions made

`ADR-0001` … `ADR-0010`.

## Deviations logged

59 rows in `docs/deviation-ledger.md`: 16 IMPROVEMENT, 25 NEUTRAL, 4 BUG-FIX, 14 DEBT
(8 repaid).

## Risks that moved

R11 privacy resolved by simulation; R19 disk never bit; R20 Metal accepted; R21–R23
Supabase risks retired by `ADR-0007`.

## Next

The owner's list is in the final message of the build session and in
`docs/14-future-work.md` §1.
