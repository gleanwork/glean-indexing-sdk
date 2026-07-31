import { defineConfig } from "@gleanwork/pluginpack";
import pkg from "./package.json" with { type: "json" };

export default defineConfig({
  name: "glean-indexing-sdk-agent-plugin",
  version: pkg.version,
  source: {
    skills: "skills",
    rootPlugin: {
      id: "connector-builder-lib",
      description: "Portable Glean Indexing SDK connector-builder skills.",
    },
  },
  metadata: {
    description: "Agent skills for building Glean Indexing SDK connectors.",
    author: {
      name: "Glean",
      email: "support@glean.com",
      url: "https://glean.com",
    },
    owner: { name: "Glean", email: "support@glean.com" },
    homepage: "https://github.com/gleanwork/glean-indexing-sdk",
    repository: "https://github.com/gleanwork/glean-indexing-sdk",
    license: "MIT",
  },
  targets: {
    claude: {
      outDir: "dist/claude",
      version: pkg.version,
      manifest: {
        description: "Glean Indexing SDK connector-builder skills for Claude Code.",
      },
      plugins: {
        "glean-connector-builder": {
          from: ["connector-builder-lib"],
          components: ["skills"],
          displayName: "Glean Connector Builder",
          description: "Build Glean Indexing SDK connectors from source-system documentation.",
        },
      },
    },
    cursor: {
      outDir: "dist/cursor",
      version: pkg.version,
      manifest: {
        metadata: {
          description: "Glean Indexing SDK connector-builder skills for Cursor.",
          keywords: ["glean", "indexing-sdk", "connectors", "skills"],
        },
      },
      plugins: {
        "glean-connector-builder": {
          from: ["connector-builder-lib"],
          components: ["skills"],
          displayName: "Glean Connector Builder",
          description: "Build Glean Indexing SDK connectors from source-system documentation.",
          manifest: {
            keywords: ["glean", "indexing-sdk", "connectors", "custom-datasources"],
            category: "developer-tools",
            tags: ["connectors", "sdk", "skills"],
          },
        },
      },
    },
  },
});
