#!/usr/bin/env node

const sdkVersion = process.argv[2];
const match = /^(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?$/.exec(sdkVersion ?? "");
if (!match) {
  throw new Error(`Unsupported SDK version ${JSON.stringify(sdkVersion)}.`);
}

const [, release, prerelease, sequence] = match;
const prereleaseName = { a: "alpha", b: "beta", rc: "rc" }[prerelease];
console.log(prereleaseName ? `${release}-${prereleaseName}.${sequence}` : release);
