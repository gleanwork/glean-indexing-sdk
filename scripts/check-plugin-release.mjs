#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function readJson(path) {
  return JSON.parse(readFileSync(new URL(`../${path}`, import.meta.url), "utf8"));
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const expectedVersion = process.argv[2];
const packageJson = readJson("package.json");
const packageLock = readJson("package-lock.json");
const releaseConfig = readJson(".release-it.json");
const miseConfig = readFileSync(new URL("../mise.toml", import.meta.url), "utf8");

assert(
  packageJson.version === packageLock.version &&
    packageJson.version === packageLock.packages?.[""]?.version,
  `Plugin package versions differ: package=${packageJson.version}, lock=${packageLock.version}, lock root=${packageLock.packages?.[""]?.version}.`,
);
if (expectedVersion) {
  assert(
    packageJson.version === expectedVersion,
    `Plugin release target and package differ: target=${expectedVersion}, package=${packageJson.version}.`,
  );
}
assert(
  packageJson.scripts?.["release:plugin"] === "release-it" &&
    packageJson.scripts?.["version:plugin"] === "node scripts/plugin-version.mjs" &&
    !packageJson.scripts?.release,
  "release-it must be an internal lockstep step with an explicit SDK-to-plugin version mapper.",
);
assert(
  miseConfig.includes('SDK_RELEASE_VERSION="$PLUGIN_VERSION" npm run release:plugin') &&
    miseConfig.includes('npm run check:plugin-release -- "$PLUGIN_VERSION"'),
  "mise run release must apply and verify the SDK-derived plugin version.",
);
assert(
  releaseConfig.git?.requireBranch === "main",
  "Lockstep releases must be restricted to main.",
);
assert(
  releaseConfig.git?.commit === false &&
    releaseConfig.git?.tag === false &&
    releaseConfig.git?.push === false,
  "release-it must leave commit, tag, and push ownership to mise run release.",
);
assert(
  releaseConfig.github?.release === false,
  "release-it must not create a second GitHub Release.",
);
assert(
  releaseConfig.npm?.publish === false,
  "The private plugin package must not be published to npm.",
);
const beforeInit = releaseConfig.hooks?.["before:init"] ?? "";
const afterBump = releaseConfig.hooks?.["after:bump"] ?? "";
assert(
  beforeInit.startsWith('test -n "$SDK_RELEASE_VERSION"') &&
    beforeInit.includes("npm run diff:plugins") &&
    !beforeInit.includes("npm run build:plugins"),
  "release-it must require the mise sentinel and detect stale output before any build.",
);
assert(
  afterBump.includes("npm run test:plugins") &&
    afterBump.includes("npm run diff:plugins") &&
    afterBump.includes('npm run check:plugin-release -- "$SDK_RELEASE_VERSION"'),
  "The plugin version bump must rebuild, validate, compare, and verify its target version.",
);

const versionScript = fileURLToPath(new URL("./plugin-version.mjs", import.meta.url));
for (const [sdk, plugin] of [
  ["1.2.3", "1.2.3"],
  ["1.2.3a4", "1.2.3-alpha.4"],
  ["1.2.3b4", "1.2.3-beta.4"],
  ["1.2.3rc4", "1.2.3-rc.4"],
]) {
  const actual = execFileSync(process.execPath, [versionScript, sdk], { encoding: "utf8" }).trim();
  assert(actual === plugin, `SDK version ${sdk} mapped to ${actual}, expected ${plugin}.`);
}

console.log(
  expectedVersion
    ? `Plugin release target matches at ${expectedVersion}.`
    : `Plugin release configuration is valid at ${packageJson.version}.`,
);
