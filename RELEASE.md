# Release Process

This document describes the release process for the Glean Connector SDK.

## Quick Start

Run the `/release` command in Claude Code for a guided release process.

## Dependencies

- [`mise`](https://mise.jdx.dev/) - Tool and task management
- [`commitizen`](https://github.com/commitizen-tools/commitizen) - Conventional commits and versioning
- [`uv`](https://github.com/astral-sh/uv) - Python package management

## Versioning

We follow [Semantic Versioning](https://semver.org/).

- **MAJOR** version for incompatible API changes
- **MINOR** version for new functionality in a backward compatible manner
- **PATCH** version for backward compatible bug fixes

Version bumps are determined automatically by commit message prefixes:
- `feat:` → MINOR bump
- `fix:` → PATCH bump
- `feat!:` or `BREAKING CHANGE:` → MAJOR bump

## Process

### 1. Ensure everything is ready for release

```bash
git checkout main
git pull origin main
mise run test
mise run lint
```

### 2. Preview the release

```bash
DRY_RUN=true mise run release
```

This will show you:
- The version bump (e.g., 0.2.0 → 0.2.1)
- The changelog entries that will be generated

### 3. Run the release

```bash
mise run release
```

This will:
- Bump the version in `pyproject.toml`
- Update `CHANGELOG.md`
- Create a git commit
- Create a git tag (e.g., `v0.2.1`)

### 4. Push to trigger automated release

```bash
git push origin main --follow-tags
```

**That's it!** Pushing the tag triggers the GitHub Actions workflow which automatically:
- Builds the package
- Creates a GitHub Release with changelog
- Publishes to PyPI

### 5. Verify the release

```bash
# Watch the workflow
gh run watch

# Verify the release was created
gh release view v0.2.1
```

Check:
- [GitHub Releases](https://github.com/gleanwork/glean-indexing-sdk/releases)
- [PyPI Package](https://pypi.org/project/glean-indexing-sdk/)
