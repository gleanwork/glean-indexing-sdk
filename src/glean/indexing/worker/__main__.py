"""Entry point for running the worker as a module.

Usage:
    cd /path/to/connector/project
    uv run python -m glean.indexing.worker
"""

from glean.indexing.worker.main import main

if __name__ == "__main__":
    main()
