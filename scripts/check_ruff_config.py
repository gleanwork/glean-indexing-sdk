#!/usr/bin/env python3
"""Verify that Ruff discovers and enforces the repository policy used by CI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "pyproject.toml"
CONTROL_FILENAME = ROOT / "_ruff_policy_control.py"
RUFF = [sys.executable, "-m", "ruff", "check", "--no-cache"]


def run_ruff(source: str) -> subprocess.CompletedProcess[str]:
    """Run Ruff through normal config discovery against an in-memory module."""
    return subprocess.run(
        [*RUFF, "--stdin-filename", str(CONTROL_FILENAME), "-"],
        cwd=ROOT,
        input=source,
        text=True,
        capture_output=True,
        check=False,
    )


def output_for(result: subprocess.CompletedProcess[str]) -> str:
    """Combine Ruff output streams for diagnostics and rule assertions."""
    return result.stdout + result.stderr


def require_pass(source: str, description: str) -> None:
    """Fail when a positive control is rejected by the discovered policy."""
    result = run_ruff(source)
    if result.returncode != 0:
        raise SystemExit(f"Ruff rejected {description}:\n{output_for(result)}")


def require_rule(source: str, rule: str, description: str) -> None:
    """Fail unless a negative control is rejected by the expected rule."""
    result = run_ruff(source)
    output = output_for(result)
    if result.returncode == 0 or rule not in output:
        raise SystemExit(f"Ruff did not reject {description} with {rule}:\n{output}")


def main() -> None:
    """Exercise config discovery, selected rules, and the line-length policy."""
    conflicting_configs = [
        path for path in (ROOT / ".ruff.toml", ROOT / "ruff.toml") if path.exists()
    ]
    if conflicting_configs:
        rendered = ", ".join(str(path.relative_to(ROOT)) for path in conflicting_configs)
        raise SystemExit(f"Conflicting root Ruff configuration found: {rendered}")

    settings = subprocess.run(
        [*RUFF, "--show-settings", str(Path(__file__).resolve())],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    settings_output = output_for(settings)
    expected_settings_path = f'Settings path: "{CONFIG}"'
    if settings.returncode != 0 or expected_settings_path not in settings_output:
        raise SystemExit(
            f"Ruff did not resolve {CONFIG.relative_to(ROOT)} as its policy:\n{settings_output}"
        )

    line_120 = 'value = "' + "x " * 55 + '"\n'
    line_161 = 'value = "' + "x " * 75 + 'x"\n'
    require_pass(line_120, "the repository's 120-column positive control")
    require_rule(line_161, "E501", "the repository's 161-column negative control")
    require_rule('print("negative control")\n', "T201", "the print negative control")


if __name__ == "__main__":
    main()
