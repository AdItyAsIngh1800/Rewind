# ADR-0002: AGPL-3.0 licensing, Ultralytics detector, and private-then-public hosting

- **Status:** Accepted
- **Date:** 2026-09-09

## Context

Three questions were entangled and had to be answered together.

The specification names a compact YOLO-family model as the detector. The dominant
implementation, Ultralytics, is licensed **AGPL-3.0**. AGPL is strongly copyleft and
reaches network use: building on Ultralytics and publishing means this repository
inherits AGPL, and anyone who runs a modified version as a network service must offer
their source.

Separately, the repository has no remote. The CI workflow cannot run, `CONTRIBUTING.md`
describes a pull-request process with nowhere to happen, and Gate 6 — "a new developer
can run the system from the repository" — has nothing to clone.

## Decision

**Licence: AGPL-3.0.** The repository adopts the same licence it inherits. The full
text is in `LICENSE`.

**Detector: keep Ultralytics YOLO.** No detector swap. The alternative — a permissively
licensed detector — would require sourcing and integrating a separate ByteTrack
implementation, which is integration work and schedule risk bought for a commercial
freedom this project does not need.

**Hosting: private GitHub repository now, public at delivery in Week 20.** CI runs from
the first push and the pull-request workflow becomes real, while the dataset,
half-finished reasoning logic and week-by-week commit history stay unpublished until
they are ready to be read.

## Alternatives considered

| Option | Why not |
|---|---|
| Permissive licence (MIT/Apache-2.0) with a permissively licensed detector — torchvision RT-DETR or YOLOX | Buys commercial reusability this project has no requirement for, at the cost of integrating a tracker by hand. The specification's own rule applies: never present a more complex path merely because it is more open. Revisit if a commercial use case appears. |
| Private repository with no licence file at all | Leaves the AGPL obligation undocumented rather than absent. The obligation arrives with the dependency, not with the licence file — writing it down is free, ignoring it is not. |
| Public from day one | Publishes an incomplete reasoning layer and an unvalidated dataset during the weeks they are most likely to be wrong. The commit history is more useful as evidence of process once there is an outcome to attach it to. |

## Consequences

**Accepted.** Anyone deploying a modified REWIND as a network service must offer their
source. For an academic project and a portfolio piece this costs nothing. Ultralytics
stays, with ByteTrack bundled, which keeps E3.1 and E3.2 to configuration rather than
integration.

**Obligations that follow.** The `LICENSE` file ships AGPL-3.0 in full. Ultralytics is
attributed in `README.md` and in `pyproject.toml`. If the project is ever run as a
hosted service, the source offer must be honoured.

**Deferred, not avoided.** If a commercial or closed-source use case appears, both the
licence and the detector have to be revisited **together** — the detector is what
forces the licence, so changing one without the other achieves nothing.

**Week 20 has a new task.** Flipping the repository to public is now an explicit
delivery step, gated on `CONTRIBUTING.md`, the PR workflow and the reasoning layer
being ready to be read by someone else.

## Validation plan

- Before the Week 20 flip: confirm `LICENSE` is present and complete, Ultralytics is
  attributed, and no third-party asset in `data/` carries an incompatible licence.
- If a commercial use case is ever raised: reopen this ADR rather than patching the
  licence in isolation.

## Related

`ROADMAP.md` E11 · `docs/00-project-charter.md` §7 · spec §C detector choice.
