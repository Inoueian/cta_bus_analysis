#!/usr/bin/env python3
"""Print each adapter's QA table on its committed fixture and diff it against the committed baseline.

specs/qa-skill.md. The cases are cta.qa_baseline.FIXTURE_CASES; the baseline is
tests/fixtures/qa_baseline.csv. Exit status 1 when any number differs, else 0. Offline: reads
tests/fixtures/ only, never the network or data/.

Examples:
  python scripts/qa.py                      every case against the baseline
  python scripts/qa.py archive              one case, against that case's baseline rows only
  python scripts/qa.py mansueto_raw --record

--record replaces the named cases' rows in the baseline (every case when none is named, which also drops
rows of a case no longer in FIXTURE_CASES) and prints the diff it accepts. Record only for a spec that
changes a threshold or exclusion, a rebuilt fixture, or a new case; never for a refactor
(.claude/skills/qa/SKILL.md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from cta import qa_baseline  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cases", nargs="*", metavar="case", help=f"cases to run (default all): {', '.join(qa_baseline.FIXTURE_CASES)}")
    ap.add_argument("--baseline", type=Path, default=qa_baseline.BASELINE_PATH, help="baseline CSV (default tests/fixtures/qa_baseline.csv)")
    ap.add_argument("--record", action="store_true", help="write the observed tables of the named cases into the baseline")
    args = ap.parse_args(argv)

    unknown = [c for c in args.cases if c not in qa_baseline.FIXTURE_CASES]
    if unknown:
        ap.error(f"unknown case(s) {unknown}; cases: {list(qa_baseline.FIXTURE_CASES)}")
    cases = [c for c in qa_baseline.FIXTURE_CASES if not args.cases or c in args.cases]

    baseline = qa_baseline.read_baseline(args.baseline) if args.baseline.is_file() else qa_baseline.empty_baseline()
    observed = {case: qa_baseline.fixture_qa(case) for case in cases}
    for case, table in observed.items():
        print(f"== {case}")
        print(table.drop(columns="case").to_string(index=False))
        print()

    diff = qa_baseline.diff_qa(pd.concat(list(observed.values()), ignore_index=True), baseline[baseline["case"].isin(cases)])
    if diff.empty:
        print(f"no difference from {args.baseline}")
    else:
        print(f"{len(diff)} cell(s) where the fixture QA differs from {args.baseline}:")
        print(diff.to_string(index=False))

    if args.record:
        kept = [observed[c] if c in observed else baseline[baseline["case"] == c] for c in qa_baseline.FIXTURE_CASES]
        qa_baseline.write_baseline(pd.concat(kept, ignore_index=True), args.baseline)
        print(f"recorded {', '.join(cases)} in {args.baseline}" + (" (the diff above is accepted)" if not diff.empty else " (nothing moved)"))
        return 0
    return 0 if diff.empty else 1


if __name__ == "__main__":
    sys.exit(main())
