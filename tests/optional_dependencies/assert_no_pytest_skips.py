"""Fail a CI lane when its pytest JUnit report contains skips or no tests."""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> None:
    """Validate that a pytest JUnit report ran tests with exactly zero skips."""
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    root = ET.parse(args.report).getroot()
    suites = list(root.iter("testsuite"))
    tests = sum(int(suite.attrib.get("tests", "0")) for suite in suites)
    skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in suites)

    if tests == 0:
        raise SystemExit("Optional dependency test lane collected zero tests")
    if skipped != 0:
        raise SystemExit(
            f"Optional dependency test lane skipped {skipped} tests; expected exactly zero"
        )


if __name__ == "__main__":
    main()
