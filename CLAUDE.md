# REWIND — working agreements

Read `ROADMAP.md` for the plan and `docs/adr/` for decisions already made. Do not
re-litigate a decision that has an ADR; if it needs revisiting, write a new ADR.

## Code documentation standard — non-negotiable

**Every module, class and function carries a docstring. Every argument and return value
is typed.** Enforced by `ruff` (`D`, `ANN`) and `mypy --strict`, both blocking in CI.

- **Docstring** — what it does and *why it exists*. Summary line, blank line, then the
  detail that is not obvious from the signature.
- **Type hints** — no implicit `Any`, no untyped defs, no bare `list` or `dict`.
  `dict[str, Any]` is fine for JSONB and event payloads; that is what `ANN401` is
  ignored for.
- **Comments** — explain *why*, never *what*. A comment restating the code is worse
  than none, because it is one more thing that drifts. Comment the reasoning a reader
  cannot recover from the code: why this threshold, why this ordering, why not the
  obvious alternative.

Docstrings here explain why a rule exists, not merely what it checks. Match that.

## Output — logging, never print

**No `print`. Anywhere.** Enforced by `ruff` (`T20`), blocking in CI.

Take a module-level `log = logging.getLogger(__name__)` and log to it. The process
entry point — the `if __name__ == "__main__":` block — calls `configure_logging()`
from `services/observability/logging.py` once, and nothing else configures handlers.

The reason is E10.2: structured logs go to an aggregator, and a `print` is invisible
there. Because every call site is already a stdlib logger, that phase swaps one
formatter in one file. A single `print` merged today is a call site someone has to
find and rewrite then.

The one exception is `scripts/dataset/build_scene.py` and `render_cases.py`, which
run inside Blender's bundled Python and cannot import this project — they call
`logging.basicConfig` inline with the same handler.

## Before claiming anything is done

```bash
make lint    # ruff check + format + mypy --strict
make test
```

Report per-check pass/fail explicitly. Do not chain gates behind `&&` where a silent
failure looks like success — that has already let a red CI through once.

## Schema authority

`packages/schemas/` is frozen. Schema flows one way:

```
Pydantic contract -> SQLAlchemy model -> Alembic migration -> database
```

Changing a contract needs a `SCHEMA_VERSION` bump, an ADR, and regenerated golden
fixtures. Supabase Studio is for reading, never for altering tables. `supabase/migrations/`
handles only RLS, storage buckets and extensions — never an application table.

After touching `apps/api/`, regenerate the contract:

```bash
make openapi
```

## Commits

`type: short specific description`, imperative, under 72 characters. One commit per
logical reason someone might revert it. Code and docs are separate commits.

## Scope

The charter (`docs/00-project-charter.md` §4) lists non-goals. Check new work against
them before building. Anything outside goes to the post-MVP backlog with a
`docs/deviation-ledger.md` row, classified IMPROVEMENT / NEUTRAL / DEBT / SCOPE-CREEP.

## When in doubt

Ask. State what the doubt is about in a sentence or two, give the options with their
trade-offs, and recommend one. Do not guess on anything that changes the plan, a
dependency, or a phase boundary.
