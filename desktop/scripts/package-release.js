const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const {
  checksumPath,
  getReleaseArtifacts,
  productName,
  verifyAppArtifact,
  verifyDmgArtifact,
  verifyZipArtifact,
} = require("./release-artifact-utils");
const {
  prepareStandaloneNativeDependencies,
} = require("./prepare-standalone-native-deps");

function parseArgs(argv) {
  const args = {
    archs: ["arm64", "x64"],
  };

  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];

    if (current === "--arch") {
      args.archs = [argv[index + 1]];
      index += 1;
      continue;
    }

    if (current.startsWith("--arch=")) {
      args.archs = [current.slice("--arch=".length)];
    }
  }

  return args;
}

function fail(message, code = 1) {
  console.error(message);
  process.exit(code);
}

function run(command, args, label, options = {}) {
  console.log(`\n[desktop:package:release] ${label}`);

  const result = spawnSync(command, args, {
    stdio: "inherit",
    env: process.env,
    ...options,
  });

  if (result.status !== 0) {
    fail(`${label} failed with exit code ${result.status || 1}`, result.status || 1);
  }
}

function ensureSupportedArchs(archs) {
  const supported = new Set(["arm64", "x64"]);
  const unknown = archs.filter((arch) => !supported.has(arch));
  if (unknown.length > 0) {
    fail(`Unsupported arch value(s): ${unknown.join(", ")}`);
  }
}

function cleanCurrentArtifacts(artifacts) {
  const cleanupTargets = new Set([checksumPath]);

  artifacts.forEach((artifact) => {
    cleanupTargets.add(artifact.zipPath);
    cleanupTargets.add(artifact.zipBlockmapPath);
    cleanupTargets.add(artifact.dmgPath);
    cleanupTargets.add(artifact.dmgBlockmapPath);
  });

  cleanupTargets.forEach((targetPath) => {
    fs.rmSync(targetPath, { force: true, recursive: true });
  });
}

function buildElectronZip(arch) {
  run(
    "npx",
    ["electron-builder", "--mac", "zip", `--${arch}`, "--publish", "never"],
    `Building signed ${arch} app + ZIP via electron-builder`,
  );
}

function createDmg(artifact) {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), `mutx-dmg-${artifact.arch}-`));
  const stageDir = path.join(tempRoot, "stage");
  const stagedAppPath = path.join(stageDir, `${productName}.app`);

  try {
    fs.mkdirSync(stageDir, { recursive: true });
    run("ditto", [artifact.appPath, stagedAppPath], `Staging ${artifact.arch} app for DMG`);
    fs.symlinkSync("/Applications", path.join(stageDir, "Applications"));

    fs.rmSync(artifact.dmgPath, { force: true });

    run(
      "hdiutil",
      [
        "create",
        "-volname",
        productName,
        "-srcfolder",
        stageDir,
        "-fs",
        "HFS+",
        "-format",
        "UDZO",
        "-ov",
        artifact.dmgPath,
      ],
      `Creating ${artifact.arch} DMG ${path.basename(artifact.dmgPath)}`,
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
}

function verifySourceArtifacts(artifact) {
  verifyAppArtifact(
    artifact.appPath,
    `${artifact.arch} app`,
    undefined,
    artifact.executableArch,
  );
  console.log(`[desktop:package:release] Verified signed ${artifact.arch} app ${artifact.appPath}`);

  verifyZipArtifact(artifact.zipPath, undefined, undefined, artifact.executableArch);
  console.log(`[desktop:package:release] Verified extracted ${artifact.arch} ZIP ${artifact.zipPath}`);
}

function verifyDmgOutput(artifact) {
  verifyDmgArtifact(artifact.dmgPath, undefined, undefined, artifact.executableArch);
  console.log(`[desktop:package:release] Verified mounted ${artifact.arch} DMG ${artifact.dmgPath}`);
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  ensureSupportedArchs(args.archs);

  const artifacts = getReleaseArtifacts(args.archs);
  cleanCurrentArtifacts(artifacts);
  prepareStandaloneNativeDependencies(args.archs);

  args.archs.forEach((arch) => buildElectronZip(arch));
  artifacts.forEach((artifact) => verifySourceArtifacts(artifact));
  artifacts.forEach((artifact) => createDmg(artifact));
  artifacts.forEach((artifact) => verifyDmgOutput(artifact));

  console.log(
    `\n[desktop:package:release] Created verified signed desktop artifacts for ${args.archs.join(", ")}.`,
  );
}

main();
