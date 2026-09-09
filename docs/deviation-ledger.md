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
| 2026-09-09 | PS-6 | Persist object-index and depth passes for ground truth | Compute ground truth in-process, emit JSON only | `IMPROVEMENT` | 0 d | Forced by R19, but better regardless — removes 8,100 intermediate files and an entire parsing step |
| 2026-09-09 | PS-2 | Frame sampling justified as GPU-load control (spec §11) | Sampling retained, but justified by reproducibility — the machine is ~10x faster than the dataset needs | `IMPROVEMENT` | 0 d | Measured 33.6 FPS at batch 1 vs 10 FPS required. R1 downgraded to Low. Bigger detector now affordable if Gate 1 recall floor is missed |
| 2026-09-09 | PS-4 | PostgreSQL 16 in a local container (spec §C) | Supabase — hosted Postgres plus Storage, Auth/RLS and pgvector | `IMPROVEMENT` | 0 d | `ADR-0003`. Not added scope: implements object storage (§C, §E2), RBAC and evidence access logging (§M), and vector search (§C) that were already committed and scheduled later. FastAPI, SQLAlchemy and `openapi.json` unchanged — all 31 tests passed without edit, which was the validation criterion |
| 2026-09-09 | PS-4 | Gate 6: clone the repo and run | Clone the repo, plus a Supabase project and credentials | `DEBT` | 0 d | New risk R23. Repaid partially by documenting the exact four values in the README. Revisit if it blocks the Gate 6 check |
| 2026-09-09 | PS-2 | Worker containerized like every other service | Worker runs on the host in development; container image CPU-only | `DEBT` | 0 d | Docker has no Metal passthrough (R20). Gate 6 criteria amended to expect CPU-only container parity |
