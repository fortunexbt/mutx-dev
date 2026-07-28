#!/usr/bin/env node

// eslint-disable-next-line @typescript-eslint/no-require-imports -- This verifier is CommonJS.
const { spawnSync } = require("node:child_process");

const STABLE_SEMVER = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const COMMIT_SHA = /^[0-9a-f]{40}$/;
const REQUEST_TIMEOUT_MS = 10_000;

function parseStableVersion(version) {
  const match = STABLE_SEMVER.exec(version);
  if (!match) {
    throw new Error(`Expected a stable semantic version, got ${JSON.stringify(version)}.`);
  }
  return match.slice(1).map((component) => BigInt(component));
}

function compareStableVersions(left, right) {
  const leftParts = parseStableVersion(left);
  const rightParts = parseStableVersion(right);
  for (let index = 0; index < leftParts.length; index += 1) {
    if (leftParts[index] < rightParts[index]) return -1;
    if (leftParts[index] > rightParts[index]) return 1;
  }
  return 0;
}

function parseReleaseIdentity(payload, label) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`${label} did not return a release identity object.`);
  }

  const keys = Object.keys(payload).sort();
  if (JSON.stringify(keys) !== JSON.stringify(["sha", "tag", "version"])) {
    throw new Error(`${label} returned an unexpected release identity shape: ${keys.join(", ")}`);
  }
  parseStableVersion(payload.version);
  if (payload.tag !== `v${payload.version}` || !COMMIT_SHA.test(payload.sha)) {
    throw new Error(`${label} returned a malformed release identity.`);
  }

  return payload;
}

async function fetchReleaseIdentity(rawUrl, label) {
  const url = new URL(rawUrl);
  if (url.protocol !== "https:") {
    throw new Error(`${label} release identity URL must use HTTPS.`);
  }
  url.searchParams.set("mutx_promotion_check", `${Date.now()}-${process.pid}`);

  const response = await fetch(url, {
    cache: "no-store",
    redirect: "manual",
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
  if (response.status !== 200) {
    throw new Error(`${label} release identity returned HTTP ${response.status}; expected 200.`);
  }
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.toLowerCase().includes("application/json")) {
    throw new Error(`${label} release identity must return application/json.`);
  }

  return parseReleaseIdentity(await response.json(), label);
}

function isAncestorCommit(ancestorSha, targetSha) {
  const result = spawnSync("git", ["merge-base", "--is-ancestor", ancestorSha, targetSha], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.status === 0) return true;
  if (result.status === 1) return false;
  const detail = `${result.stdout || ""}${result.stderr || ""}`.trim();
  throw new Error(
    `Unable to validate production commit ancestry ${ancestorSha} -> ${targetSha}` +
      (detail ? `: ${detail}` : "."),
  );
}

async function assertProductionIsNotDowngraded(
  targetVersion,
  targetSha,
  apiUrl,
  frontendUrl,
  { isAncestor = isAncestorCommit } = {},
) {
  parseStableVersion(targetVersion);
  if (!COMMIT_SHA.test(targetSha)) {
    throw new Error("Target release commit must be a full lowercase Git SHA.");
  }
  const surfaces = await Promise.all([
    fetchReleaseIdentity(apiUrl, "API").then((identity) => ({ identity, label: "API" })),
    fetchReleaseIdentity(frontendUrl, "frontend").then((identity) => ({
      identity,
      label: "frontend",
    })),
  ]);
  const newestCurrent = surfaces.reduce((newest, surface) =>
    compareStableVersions(surface.identity.version, newest.identity.version) > 0
      ? surface
      : newest,
  );

  if (compareStableVersions(targetVersion, newestCurrent.identity.version) < 0) {
    throw new Error(
      `Refusing production downgrade from ${newestCurrent.identity.version} to ${targetVersion}.`,
    );
  }

  if (compareStableVersions(targetVersion, newestCurrent.identity.version) === 0) {
    for (const { identity, label } of surfaces) {
      if (compareStableVersions(targetVersion, identity.version) !== 0) continue;
      if (identity.sha === targetSha) continue;
      if (!isAncestor(identity.sha, targetSha)) {
        throw new Error(
          `Refusing same-version production promotion for ${targetVersion}: ${label} commit ` +
            `${identity.sha} is neither ${targetSha} nor its ancestor.`,
        );
      }
    }
    console.log(
      `Same-version production recovery is commit-bound and forward-only for ${targetVersion}.`,
    );
  } else {
    console.log(
      `Production upgrade ${newestCurrent.identity.version} -> ${targetVersion} is allowed.`,
    );
  }
}

async function main() {
  const [targetVersion, targetSha, apiUrl, frontendUrl] = process.argv.slice(2);
  if (!targetVersion || !targetSha || !apiUrl || !frontendUrl) {
    throw new Error(
      "Usage: node scripts/check-production-version.cjs <target-version> <target-sha> " +
        "<api-identity-url> <frontend-identity-url>",
    );
  }
  await assertProductionIsNotDowngraded(targetVersion, targetSha, apiUrl, frontendUrl);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}

module.exports = {
  assertProductionIsNotDowngraded,
  compareStableVersions,
  fetchReleaseIdentity,
  isAncestorCommit,
  parseReleaseIdentity,
  parseStableVersion,
};
