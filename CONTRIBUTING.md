# Contributing to the Glean Connector SDK

Thank you for your interest in contributing to the Glean Connector SDK! This document provides guidelines and instructions for contributing to this project.

## Setup

1. Clone the repository
2. Set up your environment:
   ```bash
   # Install go-task if not already installed
   brew install go-task

   # Set up development environment
   task setup
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
   task lint:fix
   task test:all
   ```

4. Commit your changes using commitizen:
   ```bash
   uv run python -m commitizen commit
   ```

5. Push your branch and create a pull request

## Code Style

We follow standard Python code styles:

- Use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting
- Use [MyPy](https://mypy.readthedocs.io) for type checking
- Follow [type hints](https://docs.python.org/3/library/typing.html) in all code

## Testing

- Write unit tests for all new functionality
- Ensure all tests pass before submitting a PR

## Release Process

We use [commitizen](https://commitizen-tools.github.io/commitizen/) for versioning:

```bash
# Perform a dry run
task release DRY_RUN=true

# Create a new release
task release
```

## Documentation

- Update documentation for any changes to public APIs
- Include docstrings for all public classes and methods

Thank you for your contributions! 