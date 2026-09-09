"""Run the benchmark harness and write a dated report.

    make bench

Scores the golden fixtures against themselves by default, which is the plumbing
self-check. Point ``--predicted`` at a real prediction directory once one exists.
"""

from __future__ import annotations

import argparse
import pathlib

from packages.evaluation.benchmark import render_markdown, run_benchmark

DEFAULT_FIXTURES = pathlib.Path("tests/fixtures/golden")
REPORTS = pathlib.Path("artifacts/benchmark-reports")


def main() -> int:
    """Run the benchmark, write the report, and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predicted", type=pathlib.Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--truth", type=pathlib.Path, default=DEFAULT_FIXTURES)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if any metric is below its threshold",
    )
    args = parser.parse_args()

    result = run_benchmark(args.predicted, args.truth)
    report = render_markdown(result)

    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = result.generated_at.strftime("%Y-%m-%dT%H%M%SZ")
    path = REPORTS / f"{stamp}.md"
    path.write_text(report)

    print(report)
    print(f"written to {path}")

    if args.strict and result.failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
