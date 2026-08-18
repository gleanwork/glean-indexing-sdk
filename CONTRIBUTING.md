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

- Use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting
- Use [Pyright](https://github.com/microsoft/pyright) for type checking
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

The bundled `glean-connector-builder` agent plugin (`skills/`, packaged with [pluginpack](https://github.com/gleanwork/pluginpack)) has its own version in the root `package.json`, separate from the SDK's version in `pyproject.toml`. Bump it whenever a skill or plugin change should reach existing installs — `claude plugin update` (and the Cursor/Codex equivalents) skip a same-version rebuild, so an unchanged version string leaves installs on stale content even after `npm run build:plugins`.

After bumping `package.json`, rebuild and update the installed copy:

```bash
npm run build:plugins
claude plugin marketplace update glean-indexing-sdk
claude plugin update glean-connector-builder@glean-indexing-sdk
```

(Cursor and Codex have equivalent plugin/marketplace update commands.)

## Documentation

- Update documentation for any changes to public APIs
- Include docstrings for all public classes and methods

Thank you for your contributions! 