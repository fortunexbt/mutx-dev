const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

function isNumericIdentifier(value) {
  return /^(0|[1-9]\d*)$/.test(value);
}

function isReleaseSemver(value) {
  if (typeof value !== "string" || value.length === 0 || value.length > 128 || value.includes("+")) {
    return false;
  }

  const separator = value.indexOf("-");
  const core = separator === -1 ? value : value.slice(0, separator);
  const prerelease = separator === -1 ? null : value.slice(separator + 1);
  const coreIdentifiers = core.split(".");
  if (coreIdentifiers.length !== 3 || !coreIdentifiers.every(isNumericIdentifier)) {
    return false;
  }
  if (prerelease === null) {
    return true;
  }

  return prerelease.split(".").every((identifier) => {
    if (!identifier || !/^[0-9A-Za-z-]+$/.test(identifier)) {
      return false;
    }
    return !/^\d+$/.test(identifier) || isNumericIdentifier(identifier);
  });
}

function expectedArtifactNames(version) {
  return [
    `MUTX-${version}-macos-arm64.dmg`,
    `MUTX-${version}-macos-x64.dmg`,
    `MUTX-${version}-macos-arm64.zip`,
    `MUTX-${version}-macos-x64.zip`,
  ];
}

function parseManifest(body, version) {
  if (body.includes("\r")) {
    throw new Error("Checksum manifest must use LF line endings.");
  }

  const lines = body.endsWith("\n") ? body.slice(0, -1).split("\n") : body.split("\n");
  const expected = new Set(expectedArtifactNames(version));
  const entries = new Map();

  if (lines.length !== expected.size) {
    throw new Error(`Checksum manifest must contain exactly ${expected.size} entries.`);
  }

  for (const line of lines) {
    const match = /^([0-9a-f]{64}) {2}([^/\s]+)$/.exec(line);
    if (!match) {
      throw new Error(`Malformed checksum manifest entry: ${JSON.stringify(line)}`);
    }

    const [, digest, filename] = match;
    if (!expected.has(filename)) {
      throw new Error(`Unexpected checksum manifest entry: ${filename}`);
    }
    if (entries.has(filename)) {
      throw new Error(`Duplicate checksum manifest entry: ${filename}`);
    }
    entries.set(filename, digest);
  }

  for (const filename of expected) {
    if (!entries.has(filename)) {
      throw new Error(`Missing checksum manifest entry: ${filename}`);
    }
  }

  return entries;
}

function sha256File(filePath) {
  return new Promise((resolve, reject) => {
    const digest = crypto.createHash("sha256");
    const input = fs.createReadStream(filePath);
    input.on("error", reject);
    input.on("data", (chunk) => digest.update(chunk));
    input.on("end", () => resolve(digest.digest("hex")));
  });
}

async function verifyManifestDirectory(directory, version, arch) {
  const manifestName = `MUTX-${version}-SHA256SUMS.txt`;
  const manifestPath = path.join(directory, manifestName);
  const manifestStats = fs.lstatSync(manifestPath);
  if (!manifestStats.isFile() || manifestStats.isSymbolicLink()) {
    throw new Error(`Checksum manifest must be a regular file: ${manifestPath}`);
  }

  const entries = parseManifest(fs.readFileSync(manifestPath, "utf8"), version);
  const selectedEntries = [...entries].filter(
    ([filename]) => !arch || filename.includes(`-macos-${arch}.`),
  );
  if (selectedEntries.length === 0) {
    throw new Error(`Checksum manifest contains no artifacts for architecture ${arch}.`);
  }

  for (const [filename, expectedDigest] of selectedEntries) {
    const artifactPath = path.join(directory, filename);
    const stats = fs.lstatSync(artifactPath);
    if (!stats.isFile() || stats.isSymbolicLink() || stats.size === 0) {
      throw new Error(`Release artifact must be a non-empty regular file: ${artifactPath}`);
    }

    const actualDigest = await sha256File(artifactPath);
    if (actualDigest !== expectedDigest) {
      throw new Error(
        `SHA-256 mismatch for ${filename}: expected ${expectedDigest}, got ${actualDigest}`,
      );
    }
    console.log(`OK   ${filename}  ${actualDigest}`);
  }
}

function parseArgs(argv) {
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    values.set(argv[index], argv[index + 1]);
  }

  const directory = values.get("--dir");
  const version = values.get("--version");
  const arch = values.get("--arch");
  if (!directory || !isReleaseSemver(version)) {
    throw new Error(
      "Usage: node desktop/scripts/verify-checksum-manifest.js --dir <path> --version <release-semver>",
    );
  }
  if (arch && !new Set(["arm64", "x64"]).has(arch)) {
    throw new Error(`Unsupported desktop architecture: ${arch}`);
  }
  return { arch, directory: path.resolve(directory), version };
}

async function main() {
  const { arch, directory, version } = parseArgs(process.argv.slice(2));
  await verifyManifestDirectory(directory, version, arch);
  console.log(`Verified the exact streamed SHA-256 desktop artifact set for ${version}.`);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}

module.exports = {
  expectedArtifactNames,
  parseManifest,
  sha256File,
  verifyManifestDirectory,
};
