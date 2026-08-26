#!/usr/bin/env python3
"""Find the nearest reachable prior tag matching the publish version grammar."""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import NoReturn

from check_publish_provenance import TAG_PATTERN


class PreviousTagError(Exception):
    """The previous release tag could not be determined safely."""


def fail(message: str) -> NoReturn:
    """Raise a previous-tag selection failure."""
    raise PreviousTagError(message)


def git(*args: str) -> str:
    """Run Git in the release checkout."""
    try:
        return subprocess.run(
            ("git", *args), check=True, capture_output=True, text=True
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        fail(error.stderr.strip() or "Git command failed")


def previous_release_tag(current_tag: str) -> str | None:
    """Return the nearest prior tag accepted by the publish provenance guard."""
    if TAG_PATTERN.fullmatch(current_tag) is None:
        fail(f"Current release tag must exactly match v<version>; got {current_tag!r}.")

    previous_commit = f"refs/tags/{current_tag}^"
    merged_tags = git("tag", "--merged", previous_commit).splitlines()
    valid_tags = [tag for tag in merged_tags if TAG_PATTERN.fullmatch(tag) is not None]
    if not valid_tags:
        return None

    match_options = [f"--match={tag}" for tag in valid_tags]
    return git("describe", "--tags", "--abbrev=0", *match_options, previous_commit)


def parse_args() -> argparse.Namespace:
    """Parse command-line inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-tag", required=True, help="Exact current release tag")
    return parser.parse_args()


def main() -> None:
    """Print the nearest valid previous release tag, if one exists."""
    previous_tag = previous_release_tag(parse_args().current_tag)
    if previous_tag is not None:
        print(previous_tag)


if __name__ == "__main__":
    try:
        main()
    except PreviousTagError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
