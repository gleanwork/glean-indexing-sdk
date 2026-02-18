"""Entry point for running the worker as a module.

Usage:
    cd /path/to/connector/project
    uv run python -m glean.indexing.worker

    # With explicit project path
    uv run python -m glean.indexing.worker --project /path/to/project
"""

import argparse
import logging
import sys
from pathlib import Path


def main() -> None:
    """Entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="Glean Indexing SDK Worker",
    )

    parser.add_argument(
        "--project",
        type=str,
        help="Path to connector project (default: current directory)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    project_path = Path(args.project) if args.project else Path.cwd()

    env_path = project_path / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path)
            logging.info(f"Loaded environment from {env_path}")
        except ImportError:
            logging.debug("python-dotenv not installed, skipping .env loading")

    from glean.indexing.worker.main import run_stdio_server

    run_stdio_server(project_path)


if __name__ == "__main__":
    main()
