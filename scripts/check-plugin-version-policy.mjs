#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const baseSha = process.argv[2];
if (!baseSha || !/^[0-9a-f]{40}$/.test(baseSha)) {
  throw new Error("Usage: check-plugin-version-policy.mjs BASE_COMMIT_SHA");
}

function baseFile(path) {
  return execFileSync("git", ["show", `${baseSha}:${path}`], { encoding: "utf8" });
}

function currentFile(path) {
  return readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
}

function versionFrom(text, pattern, label) {
  const version = pattern.exec(text)?.[1];
  if (!version) {
    throw new Error(`Could not read ${label} version.`);
  }
  return version;
}

const sources = [
  {
    label: "plugin package",
    path: "package.json",
    read: (text) => JSON.parse(text).version,
  },
  {
    label: "Python project",
    path: "pyproject.toml",
    read: (text) => versionFrom(text, /^\[project\]\s*$[\s\S]*?^version\s*=\s*"([^"]+)"/m, "Python project"),
  },
  {
    label: "Commitizen",
    path: ".cz.toml",
    read: (text) => versionFrom(text, /^\[tool\.commitizen\]\s*$[\s\S]*?^version\s*=\s*"([^"]+)"/m, "Commitizen"),
  },
  {
    label: "Python module",
    path: "src/glean/indexing/__init__.py",
    read: (text) => versionFrom(text, /^\s*__version__\s*=\s*"([^"]+)"/m, "Python module"),
  },
];

for (const source of sources) {
  const before = source.read(baseFile(source.path));
  const current = source.read(currentFile(source.path));
  if (before !== current) {
    throw new Error(
      `Feature PRs must not change the ${source.label} version (${before} -> ${current}); mise run release updates all versions together.`,
    );
  }
}

const sdkVersions = sources.slice(1).map((source) => source.read(currentFile(source.path)));
if (new Set(sdkVersions).size !== 1) {
  throw new Error(`SDK version sources differ: ${sdkVersions.join(", ")}.`);
}

console.log(`Feature PR preserves plugin ${sources[0].read(currentFile("package.json"))} and SDK ${sdkVersions[0]} release versions.`);
