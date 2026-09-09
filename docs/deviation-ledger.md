# Deviation ledger

Every departure from `ROADMAP.md` gets a row. Deviation is normal and often correct —
**unclassified** deviation is how a project silently becomes something else.

| Class | Meaning | Action |
|---|---|---|
| `IMPROVEMENT` | Better than planned | Amend the roadmap; keep for the final report |
| `NEUTRAL` | Equivalent path | Record and move on |
| `DEBT` | Worse; needs paying back | Set a repayment date |
| `SCOPE-CREEP` | Outside the charter | Straight to the post-MVP backlog |

---

| Date | Sub-phase | Planned | Actual | Class | Cost | Action |
|---|---|---|---|---|---|---|
| 2026-09-09 | PS-3 | Repo skeleton per spec §I | Added `docs/dataset/`, `docs/weekly/`, `docs/ui/` beyond the spec tree | `IMPROVEMENT` | 0 d | Roadmap amended; these hold PS-6, PS-8 and the weekly log |
| 2026-09-09 | PS-2 | RTX 4050, 6 GB VRAM, CUDA, mixed precision (spec §H) | Apple M4, 16 GB unified memory, Metal/MPS, float32 | `NEUTRAL` | 0 d | Spec §H superseded by `docs/09-deployment.md`. Risk R1 rewritten: the failure mode is silent paging, not a clean OOM |
| 2026-09-09 | PS-2 | At least 200 GB free disk (spec §H) | 32 GB free | `DEBT` | 0 d | New risk R19. Partly repaid by never persisting Blender passes (~10 GB saved). Escalates below 15 GB free |
| 2026-09-09 | PS-8 | Five evidence states separated by hue | Separated by a lightness ladder; hue is a secondary channel | `IMPROVEMENT` | 0 d | Forced by verification failure under protanopia and tritanopia. Lightness separation survives every CVD type, greyscale and print, which hue never could |
| 2026-09-09 | PS-8 | Design tokens hand-written | Generated from the verified source by `make tokens` | `IMPROVEMENT` | 0 d | Same principle as the golden fixtures: the values shipped to the browser are exactly the values that were checked, enforced by a drift test |
| 2026-09-09 | PS-5 | API contract per specification §F | Added `GET /api/v1/cases` | `NEUTRAL` | 0 d | §F is incomplete: §G mandates a Case Inbox filtering incidents by severity, time, location and status, which no endpoint in §F could serve |
| 2026-09-09 | E3.1 | Pretrained COCO detector covers the four entity classes | COCO covers `person` only; `yolo11n` will be fine-tuned on the tuning cases | `NEUTRAL` | +0.5 d | `ADR-0004`. Verified against `yolo11n.pt`, not assumed. Charter non-goal clarified: from-scratch training stays out, fine-tuning is in. Closed-loop limitation (train and test on one synthetic scene) recorded in the ADR and to be repeated in the model card |
| 2026-09-09 | PS-6 | Racking loaded as in the visual references | Racking stays dense but carries no visible pallets | `IMPROVEMENT` | 0 d | Removes an annotation ambiguity at source rather than caveating every precision figure. `world_z < 0.5` filter kept as a safety net, plus a manual render inspection step |
| 2026-09-09 | PS-2 | 32 GB free disk, R19 High | 53 GB free after `docker system prune -a` reclaimed 25 GB | `IMPROVEMENT` | 0 d | R19 downgraded High to Low. The pass-persistence decision stands anyway — it removes 8,100 intermediate files, which is worth doing on its own merits |
| 2026-09-09 | PS-6 | Persist object-index and depth passes for ground truth | Compute ground truth in-process, emit JSON only | `IMPROVEMENT` | 0 d | Forced by R19, but better regardless — removes 8,100 intermediate files and an entire parsing step |
| 2026-09-09 | PS-2 | Frame sampling justified as GPU-load control (spec §11) | Sampling retained, but justified by reproducibility — the machine is ~10x faster than the dataset needs | `IMPROVEMENT` | 0 d | Measured 33.6 FPS at batch 1 vs 10 FPS required. R1 downgraded to Low. Bigger detector now affordable if Gate 1 recall floor is missed |
| 2026-09-09 | PS-4 | PostgreSQL 16 in a local container (spec §C) | Supabase — hosted Postgres plus Storage, Auth/RLS and pgvector | `IMPROVEMENT` | 0 d | `ADR-0003`. Not added scope: implements object storage (§C, §E2), RBAC and evidence access logging (§M), and vector search (§C) that were already committed and scheduled later. FastAPI, SQLAlchemy and `openapi.json` unchanged — all 31 tests passed without edit, which was the validation criterion |
| 2026-09-09 | PS-4 | RLS policies designed in E10.3 | RLS *enabled* deny-by-default now; policies still designed in E10.3 | `IMPROVEMENT` | 0 d | Enabling with no policy denies everything except the service role — the safe default, verified by probe: service role sees a row, anon key sees `[]`. `make verify-security` makes a future unprotected table loud |
| 2026-09-09 | PS-4 | Gate 6: clone the repo and run | Clone the repo, plus a Supabase project and credentials | `DEBT` | 0 d | New risk R23. Repaid partially by documenting the exact four values in the README. Revisit if it blocks the Gate 6 check |
| 2026-09-09 | PS-2 | Worker containerized like every other service | Worker runs on the host in development; container image CPU-only | `DEBT` | 0 d | Docker has no Metal passthrough (R20). Gate 6 criteria amended to expect CPU-only container parity |
| 2026-09-09 | PS-3 | CI integration tests against an ephemeral `postgres:16` container (`ADR-0003`) | Ephemeral `pgvector/pgvector:pg16`, plus the `vector` extension and `search_path` mirrored from `supabase/migrations` | `IMPROVEMENT` | 0 d | Same engine but a different extension set meant an unqualified `vector` column type would resolve on Supabase and fail in CI — hermetic and wrong, which is harder to spot than a red build. `ADR-0003` test isolation is unchanged: CI still never touches the hosted project. Verified by `create table t (id int, emb vector(3))` on a fresh connection, plus 135 tests and both migrations against the image |
