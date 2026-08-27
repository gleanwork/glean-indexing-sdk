# Contributing to the Glean Connector SDK

Thank you for your interest in contributing to the Glean Connector SDK! This document provides guidelines and instructions for contributing to this project.

## Setup

1. Clone the repository
2. Set up your environment:
   ```bash
   # Install mise if not already installed
   brew install mise

   # Set up development environment
   mise run setup
   ```

## Development Workflow

We use the following workflow for development:

1. Create a new branch for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes

3. Run linting and tests:
   ```bash
   mise run lint:fix
   mise run test:all
   ```

4. Commit your changes using commitizen:
   ```bash
   uv run python -m commitizen commit
   ```

5. Push your branch and create a pull request

## Code Style

We follow standard Python code styles:

- Use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting. `pyproject.toml` is the single authoritative Ruff configuration; it retains the existing 100-column formatter width and enforces the repository's 160-column lint ceiling. Do not add a separate `.ruff.toml` or `ruff.toml`.
- Ruff enforces `E`, `F`, `I`, `W`, `N`, and `T201`, plus the explicit debt-free `D` and `UP` rules listed in `pyproject.toml`. Test-only exceptions are scoped there; broader docstring and modernization families are deferred rather than selected and globally ignored.
- Use [Pyright](https://github.com/microsoft/pyright) in basic mode as the typing gate. Ruff's `ANN` family is deferred until existing annotation debt can be addressed intentionally.
- Follow [type hints](https://docs.python.org/3/library/typing.html) in all code

## Testing

- Write unit tests for all new functionality
- Ensure all tests pass before submitting a PR

## Release Process

We use [commitizen](https://commitizen-tools.github.io/commitizen/) for versioning:

```bash
# Perform a dry run
DRY_RUN=true mise run release

# Create a new release
mise run release
```

## Agent plugin versioning

The bundled `glean-connector-builder` agent plugin (`skills/`, packaged with [pluginpack](https://github.com/gleanwork/pluginpack)) is released in lockstep with the SDK. Feature PRs must rebuild committed plugin artifacts but must not change their version. Existing installs intentionally receive accumulated skill changes only when a new SDK version is released.

Always use the shared release task:

```bash
DRY_RUN=true mise run release
mise run release
```

Commitizen selects the next SDK version. The task then uses [release-it](https://github.com/release-it/release-it) to apply the same semantic version to `package.json`, `package-lock.json`, and every generated plugin manifest before amending the SDK release commit and repointing its single annotated `vX.Y.Z` tag. GA versions are identical; Python prereleases are normalized to npm syntax (`1.0.0rc1` → `1.0.0-rc.1`). There is no independently selected plugin version, tag, GitHub Release, or npm publication.

After the release, update a local Claude install with:

```bash
claude plugin marketplace update glean-indexing-sdk
claude plugin update glean-connector-builder@glean-indexing-sdk
```

(Cursor and Codex have equivalent plugin/marketplace update commands.)

## Documentation

- Update documentation for any changes to public APIs
- Include docstrings for all public classes and methods

Thank you for your contributions! 