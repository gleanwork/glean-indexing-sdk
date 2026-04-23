## v1.0.0b2 (2026-04-23)

### Feat

- add ConnectorOptions for bulk indexing configuration

### Fix

- sync markdown doc with reformatted snippet import order
- use attribute access in configure_datasource() to avoid camelCase kwargs

## v1.0.0b1 (2026-03-05)

### Feat

- support GLEAN_SERVER_URL with GLEAN_INSTANCE fallback (#14)

## v1.0.0b0 (2026-02-23)

### Feat

- add custom exception hierarchy for improved error handling

### Fix

- replace broken documentation URLs with valid ones

## v0.3.1 (2026-02-04)

### Fix

- **release**: include CHANGELOG.md and uv.lock in release commit

## v0.3.0 (2026-02-04)

### Feat

- add /release command for guided release process

### Fix

- use mise use to set Python version instead of overriding mise_toml

### Refactor

- remove legacy class aliases and standardize naming
- rename async classes to use Base prefix consistently
- rename async streaming files to follow base_* naming convention

## v0.2.0 (2025-07-24)

### Feat

- Adds support for forced restarts of indexing uploads

## v0.1.0 (2025-07-23)

### Feat

- Adds property definition builder

### Fix

- Fixing format of tags for release
- Adds addition model for re-export
