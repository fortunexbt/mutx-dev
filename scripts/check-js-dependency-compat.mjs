import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";

const require = createRequire(import.meta.url);
const packageManifests = readdirSync("node_modules", {
  encoding: "utf8",
  recursive: true,
})
  .filter((entry) => entry.endsWith("package.json"))
  .map((entry) => resolve("node_modules", entry));

const readManifest = (path) => JSON.parse(readFileSync(path, "utf8"));
const compareVersions = (left, right) => {
  const leftParts = left.split(".").map(Number);
  const rightParts = right.split(".").map(Number);

  for (let index = 0; index < 3; index += 1) {
    const delta = (leftParts[index] ?? 0) - (rightParts[index] ?? 0);
    if (delta !== 0) return delta;
  }

  return 0;
};

const braceManifests = packageManifests.filter(
  (path) => readManifest(path).name === "brace-expansion",
);

if (braceManifests.length === 0) {
  throw new Error("No installed brace-expansion packages found");
}

for (const manifestPath of braceManifests) {
  const { version } = readManifest(manifestPath);
  const major = Number(version.split(".")[0]);
  // Patched release lines for GHSA-3jxr-9vmj-r5cp.
  const minimum = major === 1 ? "1.1.16" : major === 2 ? "2.1.2" : "5.0.7";

  if (
    !Number.isInteger(major) ||
    major < 1 ||
    compareVersions(version, minimum) < 0
  ) {
    throw new Error(`Unpatched brace-expansion ${version} at ${manifestPath}`);
  }
}

const minimatchManifests = packageManifests.filter(
  (path) => readManifest(path).name === "minimatch",
);

if (minimatchManifests.length === 0) {
  throw new Error("No installed minimatch packages found");
}

for (const manifestPath of minimatchManifests) {
  const { version } = readManifest(manifestPath);
  const loaded = require(dirname(manifestPath));
  const match =
    typeof loaded === "function"
      ? loaded
      : (loaded.minimatch ?? loaded.default);

  if (typeof match !== "function") {
    throw new Error(`No callable minimatch export for ${version}`);
  }

  if (
    !match("src/index.ts", "src/**/*.ts") ||
    match("README.md", "src/**/*.ts")
  ) {
    throw new Error(`minimatch ${version} failed its compatibility probe`);
  }
}

const braceVersions = [
  ...new Set(braceManifests.map((path) => readManifest(path).version)),
]
  .sort(compareVersions)
  .join(", ");
console.log(
  `Dependency compatibility passed: brace-expansion ${braceVersions}; ${minimatchManifests.length} minimatch installation(s) probed.`,
);
