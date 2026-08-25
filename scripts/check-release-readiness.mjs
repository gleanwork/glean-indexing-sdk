#!/usr/bin/env node
import { execFileSync } from "node:child_process";

function git(...args) {
  return execFileSync("git", args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const branch = git("branch", "--show-current");
assert(branch === "main", `Releases must run from main, not ${branch || "a detached HEAD"}.`);

const status = git("status", "--porcelain", "--untracked-files=all");
assert(!status, `Releases require a clean tree, including no untracked files:\n${status}`);

git("fetch", "--quiet", "origin", "main");
const head = git("rev-parse", "HEAD");
const originMain = git("rev-parse", "origin/main");
assert(head === originMain, "Local main must exactly match origin/main before releasing.");

console.log("Release checkout is clean and matches origin/main.");
