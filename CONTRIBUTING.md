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

## Before you push

```
make lint
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
