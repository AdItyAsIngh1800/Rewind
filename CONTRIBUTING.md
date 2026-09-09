# Contributing

This is a single-maintainer academic project, but it follows a real change-control
process because traceability is one of its deliverables.

## The rule

Every meaningful change must be recoverable. Tiny changes are captured at the
smallest appropriate level — not every threshold tweak needs an ADR.

| Artifact | Required when | Records |
|---|---|---|
| Issue / task | Every feature, bug or investigation | Problem, acceptance criteria, status |
| Git commit | Every code or config change | What changed and why |
| Pull request | Every non-trivial change | Context, implementation, tests, metrics |
| Experiment record | Every ML experiment | Hypothesis, data, model, config, metrics, result |
| ADR | Architecture or technology decision | Context, options, decision, consequences |
| CHANGELOG entry | User-visible behaviour change | What changed for users |
| Weekly log | Every week | Progress, failures, decisions, risks, next steps |
| Model card | Each promoted model | Purpose, data, metrics, limitations, version |

## Commit messages

`type: short specific description`, imperative mood, under 72 characters.
Types: `feat`, `fix`, `docs`, `test`, `chore`, `refactor`, `style`.

One commit per logical reason someone might need to revert it. Adding code and
updating the README are always two commits.

## Code documentation standard

**Every module, class and function carries a docstring, and every argument and return
value is typed.** This is enforced by `ruff` (rules `D` and `ANN`) and `mypy --strict`,
both blocking in CI. It is not a style preference that can be skipped when busy — an
undocumented function fails the build.

What each part is for:

| | Answers |
|---|---|
| **Docstring** | *What* this does and *why it exists*. One-line summary, then a blank line, then the detail that is not obvious from the signature. |
| **Type hints** | *What shapes go in and come out.* `mypy --strict` means no implicit `Any`, no untyped defs, no bare `list` or `dict`. |
| **Comments** | *Why the code is like this.* Non-obvious constraints, an ordering that matters, a workaround and the thing it works around. |

A note on comments, because "comment everything" is easy to misread: a comment that
restates the code is worse than no comment, because it is one more thing that can drift
out of date. `# increment the counter` above `count += 1` costs attention and adds
nothing. Comment the reasoning a reader cannot recover from the code — why this
threshold, why this order, why not the obvious alternative.

Docstrings that earn their place in this codebase explain *why a rule exists*, not just
what it does. `Claim._must_cite_unless_unknown` does not say "validates evidence refs";
it says why an UNKNOWN claim is exempt. That is the difference between documentation and
noise.

## Before you push

```
make lint    # ruff check + format + mypy --strict
make test
```

## Changing a frozen contract

`packages/schemas/` is frozen as of PS-4. Changing a field there requires:

1. A `schema_version` bump on the affected model.
2. An ADR explaining why the contract moved.
3. Regenerated golden fixtures in `tests/fixtures/golden/`.

A silent schema change is the one failure mode this project's architecture exists
to prevent. It will be caught at the next gate review either way — catching it
yourself is cheaper.
