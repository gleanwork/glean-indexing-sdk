# Release Process

Guide the user through releasing a new version of the Glean Indexing SDK.

## Instructions

Follow these steps to release a new version:

### Step 1: Pre-flight Checks

Run the following checks to ensure the codebase is ready for release:

1. **Check git status**: Ensure working directory is clean and on `main` branch
2. **Pull latest**: `git pull origin main`
3. **Run tests**: `mise run test`
4. **Run linting**: `mise run lint`

If any checks fail, stop and fix the issues before proceeding.

### Step 2: Preview the Release

Run a dry-run to see what version bump will occur and what the changelog will look like:

```bash
DRY_RUN=true mise run release
```

Show the user:
- The current version (from `pyproject.toml`)
- The new version that will be created
- The changelog entries that will be added

Ask the user to confirm they want to proceed with the release.

### Step 3: Create the Release

If the user confirms, run the actual release:

```bash
mise run release
```

This will:
- Bump the version in `pyproject.toml`
- Update `CHANGELOG.md`
- Create a git commit with the version bump
- Create a git tag (e.g., `v0.2.1`)

### Step 4: Push to Remote

Push the commit and tag to the remote:

```bash
git push origin main --follow-tags
```

**Important:** Pushing the tag triggers the GitHub Actions workflow (`.github/workflows/publish.yml`) which automatically:
- Builds the package
- Creates a GitHub Release with changelog
- Publishes to PyPI

### Step 5: Verify the Release

After pushing, guide the user to verify:

1. Check the GitHub Actions workflow is running: `gh run list --limit 3`
2. Watch the workflow: `gh run watch`
3. Once complete, verify:
   - GitHub Release exists: `gh release view vX.Y.Z`
   - PyPI package is published: https://pypi.org/project/glean-indexing-sdk/

## Summary

At the end, provide a summary:
- New version number
- Link to the GitHub release: https://github.com/gleanwork/glean-indexing-sdk/releases/tag/vX.Y.Z
- Link to PyPI: https://pypi.org/project/glean-indexing-sdk/X.Y.Z/
