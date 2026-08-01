import { defineConfig } from "@gleanwork/pluginpack";
import pkg from "./package.json" with { type: "json" };

// Every host reads its marketplace manifest at the root of the repo it is
// pointed at, and none of them accept an `owner/repo/subpath` form — so the
// manifests have to land at the repo root for `gleanwork/glean-indexing-sdk` to
// be installable directly.
//
// The emitted plugin content under build/ is committed rather than ignored:
// each manifest's `source` points at it, so it has to exist in a fresh clone —
// that clone is exactly what `claude plugin marketplace add
// gleanwork/glean-indexing-sdk` gets. Same arrangement as
// gleanwork/glean-cookbook and gleanwork/claude-plugins, both of which also
// commit generated output. Editing a skill therefore changes its source under
// skills/ and the three emitted copies; regenerate with `npm run build:plugins`
// rather than editing anything under build/ directly. CI fails on drift.
//
// Claude, Cursor, and Codex each write a different marketplace path, so those
// don't collide at the shared root — but claude and codex both default to
// `plugins/<name>` for content, hence the explicit per-target paths below.

// Fields the host reads off the marketplace entry. Without `version` it falls
// back to the git commit SHA, which would make every skill edit register as a
// new plugin version.
const ENTRY_METADATA = {
  version: pkg.version,
  author: { name: "Glean" },
  homepage: "https://developers.glean.com/libraries/indexing-sdk",
  repository: "https://github.com/gleanwork/glean-indexing-sdk",
  license: "MIT",
};

const entry = { ...ENTRY_METADATA };

// Codex requires these on the marketplace entry and pluginpack can't derive
// them. `ON_USE` rather than `ON_INSTALL`: installing collects no credential —
// the connector builder asks for a Glean token when you actually index.
const codexEntry = {
  ...ENTRY_METADATA,
  policy: { installation: "AVAILABLE", authentication: "ON_USE" },
  category: "Developer Tools",
};

const PLUGIN_DESCRIPTION =
  "Build a Glean connector from a description of your source: explore its API, plan, generate against the Indexing SDK, and test.";

export default defineConfig({
  name: "glean-indexing-sdk",
  version: pkg.version,
  source: {
    skills: "skills",
    rootPlugin: {
      id: "connector-builder-lib",
      description: "Portable Glean Indexing SDK connector-builder skills.",
    },
  },
  metadata: {
    description:
      "Build Glean Indexing SDK connectors hands-free from Claude Code, Cursor, or Codex.",
    author: {
      name: "Glean",
      email: "support@glean.com",
      url: "https://glean.com",
    },
    owner: { name: "Glean", email: "support@glean.com" },
    homepage: "https://developers.glean.com/libraries/indexing-sdk",
    repository: "https://github.com/gleanwork/glean-indexing-sdk",
    license: "MIT",
  },
  targets: {
    claude: {
      outDir: ".",
      marketplaceDir: ".claude-plugin",
      pluginRoot: "build/claude",
      plugins: {
        "glean-connector-builder": {
          from: ["connector-builder-lib"],
          components: ["skills"],
          displayName: "Glean Connector Builder",
          description: PLUGIN_DESCRIPTION,
          entry,
        },
      },
    },
    cursor: {
      outDir: ".",
      marketplaceDir: ".cursor-plugin",
      plugins: {
        "glean-connector-builder": {
          from: ["connector-builder-lib"],
          components: ["skills"],
          path: "build/cursor/glean-connector-builder",
          displayName: "Glean Connector Builder",
          description: PLUGIN_DESCRIPTION,
          entry,
          manifest: {
            keywords: ["glean", "indexing-sdk", "connectors", "custom-datasources"],
            category: "developer-tools",
            tags: ["connectors", "sdk", "skills"],
          },
        },
      },
    },
    codex: {
      outDir: ".",
      marketplaceDir: ".agents/plugins",
      plugins: {
        "glean-connector-builder": {
          from: ["connector-builder-lib"],
          components: ["skills"],
          path: "build/codex/glean-connector-builder",
          displayName: "Glean Connector Builder",
          description: PLUGIN_DESCRIPTION,
          entry: codexEntry,
        },
      },
    },
  },
});
