# Release Process

This document describes the release process for the Glean Connector SDK.

## Quick Start

Run the `/release` command in Claude Code for a guided release process.

## Dependencies

- [`mise`](https://mise.jdx.dev/) - Tool and task management
- [`commitizen`](https://github.com/commitizen-tools/commitizen) - Conventional commits and versioning
- [`uv`](https://github.com/astral-sh/uv) - Python package management
- [`release-it`](https://github.com/release-it/release-it) - Agent plugin version synchronization and rebuild

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
- The shared SDK/plugin version bump (e.g., 0.2.0 → 0.2.1)
- The changelog entries that will be generated
- The plugin package and generated artifacts release-it would update

### 3. Run the release

```bash
mise run release
```

This will:
- Bump the SDK version in `pyproject.toml`
- Apply the same version to the plugin package, lockfile, and generated manifests
- Rebuild and validate Claude, Cursor, and Codex plugin artifacts
- Update `CHANGELOG.md` and `uv.lock`
- Create one release commit and one tag (e.g., `v0.2.1`)

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

## Agent plugin releases

The bundled agent plugin is part of the SDK release, not an independent product release. Feature PRs rebuild its committed artifacts without changing their version. `mise run release` applies the same semantic version to the plugin package, lockfile, and all generated manifests in the SDK release commit. GA versions are identical; Python prereleases are normalized to npm syntax (`1.0.0rc1` → `1.0.0-rc.1`).

Release-it performs only the plugin version update and rebuild. Commitizen and the mise task retain ownership of the single release commit, annotated `vX.Y.Z` tag, changelog, GitHub Release, and PyPI publication. The private plugin package is not published to npm. If any post-bump step fails, the task restores the starting commit and removes the incomplete tag.
