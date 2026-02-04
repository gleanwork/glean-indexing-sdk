# Release Process

This document describes the release process for the Glean Connector SDK.

## Dependencies

- [`mise`](https://mise.jdx.dev/) - Tool and task management
- [`commitizen`](https://github.com/commitizen-tools/commitizen) - Conventional commits and versioning
- [`uv`](https://github.com/astral-sh/uv) - Python package management

## Versioning

We follow [Semantic Versioning](https://semver.org/).

- **MAJOR** version for incompatible API changes
- **MINOR** version for new functionality in a backward compatible manner
- **PATCH** version for backward compatible bug fixes

## Process

### 1. Ensure everything is ready for release

- All tests are passing
- Documentation is up to date
- Changelog has been updated

### 2. Create a release branch

```bash
git checkout -b release/vX.Y.Z
```

### 3. Run the release task

First, perform a dry run to verify the release:

```bash
DRY_RUN=true mise run release
```

This will show you what changes will be made without applying them.

Then, run the actual release:

```bash
mise run release
```

This will:

- Bump the version based on commit messages
- Generate/update the changelog
- Create a git tag
- Commit the changes

### 4. Push the changes

```bash
git push origin release/vX.Y.Z
git push origin vX.Y.Z
```

### 5. Create a pull request

- Create a PR from the release branch to main
- Have it reviewed and approved
- Merge the PR

### 6. Build and publish

After the PR is merged:

```bash
git checkout main
git pull
mise run build
mise run publish
```

This will build the package and upload it to PyPI.

### 7. Create a GitHub release

- Go to the GitHub releases page
- Create a new release using the tag
- Copy the relevant section from CHANGELOG.md as the release description
- Publish the release
