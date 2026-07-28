const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const packageJson = require("../../package.json");
const {
  getReleaseArtifacts,
  verifyAppArtifact,
  verifyDmgArtifact,
} = require("./release-artifact-utils");
const productName = packageJson.build?.productName || packageJson.name;
const distDir = path.resolve(__dirname, "../../dist/desktop");

function run(command, args) {
  return spawnSync(command, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function getOutput(result) {
  return `${result.stdout || ""}${result.stderr || ""}`.trim();
}

function getLastLine(result) {
  const lines = getOutput(result)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines[lines.length - 1] || "(no output)";
}

function isInsufficientContext(result) {
  return getOutput(result).includes("source=Insufficient Context");
}

function formatError(error) {
  const message = error instanceof Error ? error.message : String(error);
  const lines = message
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines[lines.length - 1] || message;
}

function readSignatureDetails(appPath) {
  const result = run("codesign", ["-dv", "--verbose=4", appPath]);
  const output = getOutput(result);
  const authority = output
    .split(/\r?\n/)
    .find((line) => line.startsWith("Authority="))
    ?.replace("Authority=", "");
  const teamId = output
    .split(/\r?\n/)
    .find((line) => line.startsWith("TeamIdentifier="))
    ?.replace("TeamIdentifier=", "");
  const timestamp = output
    .split(/\r?\n/)
    .find((line) => line.startsWith("Timestamp="))
    ?.replace("Timestamp=", "");

  return {
    authority: authority || "unknown",
    teamId: teamId || "unknown",
    timestamp: timestamp || "unknown",
  };
}

function findApps() {
  return getReleaseArtifacts()
    .filter((artifact) => fs.existsSync(artifact.appPath))
    .sort(
      (left, right) => fs.statSync(right.appPath).mtimeMs - fs.statSync(left.appPath).mtimeMs,
    );
}

function findDmgs() {
  return getReleaseArtifacts()
    .filter((artifact) => fs.existsSync(artifact.dmgPath))
    .sort((left, right) => {
      const leftTime = fs.statSync(left.dmgPath).mtimeMs;
      const rightTime = fs.statSync(right.dmgPath).mtimeMs;
      return rightTime - leftTime;
    });
}

function checkApp(appPath, expectedArch) {
  const details = readSignatureDetails(appPath);
  let signatureOk = true;
  let signatureMessage = "valid signature";
  try {
    verifyAppArtifact(appPath, `${path.basename(appPath)} bundle`, undefined, expectedArch);
  } catch (error) {
    signatureOk = false;
    signatureMessage = formatError(error);
  }
  const gatekeeper = run("spctl", ["--assess", "--type", "execute", "--verbose=4", appPath]);
  const staple = run("xcrun", ["stapler", "validate", appPath]);
  const ok = signatureOk && gatekeeper.status === 0 && staple.status === 0;

  console.log(`\nAPP  ${appPath}`);
  console.log(`  signed by: ${details.authority}`);
  console.log(`  team id:   ${details.teamId}`);
  console.log(`  timestamp: ${details.timestamp}`);
  console.log(`  codesign:  ${signatureMessage}`);
  console.log(`  gatekeeper:${gatekeeper.status === 0 ? " accepted" : ` ${getLastLine(gatekeeper)}`}`);
  console.log(`  stapler:   ${staple.status === 0 ? "ticket stapled" : getLastLine(staple)}`);

  return ok;
}

function checkDmg(dmgPath, expectedArch) {
  let mountedAppOk = true;
  let mountedAppMessage = "valid nested signature";
  try {
    verifyDmgArtifact(dmgPath, undefined, undefined, expectedArch);
  } catch (error) {
    mountedAppOk = false;
    mountedAppMessage = formatError(error);
  }
  const gatekeeper = run("spctl", ["--assess", "--type", "open", "--verbose=4", dmgPath]);
  const staple = run("xcrun", ["stapler", "validate", dmgPath]);
  const ok =
    mountedAppOk && staple.status === 0 && (gatekeeper.status === 0 || isInsufficientContext(gatekeeper));

  console.log(`\nDMG  ${dmgPath}`);
  console.log(`  mounted app:${mountedAppOk ? " valid nested signature" : ` ${mountedAppMessage}`}`);
  console.log(`  gatekeeper:${gatekeeper.status === 0 ? " accepted" : ` ${getLastLine(gatekeeper)}`}`);
  console.log(`  stapler:   ${staple.status === 0 ? "ticket stapled" : getLastLine(staple)}`);

  return ok;
}

function main() {
  const apps = findApps();
  const dmgs = findDmgs();

  if (apps.length === 0 && dmgs.length === 0) {
    console.error(`No macOS artifacts found under ${distDir}`);
    process.exit(1);
  }

  console.log(`Checking notarization status for ${productName} artifacts in ${distDir}`);

  const failures = [];

  apps.forEach((artifact) => {
    if (!checkApp(artifact.appPath, artifact.executableArch)) {
      failures.push(artifact.appPath);
    }
  });

  dmgs.forEach((artifact) => {
    if (!checkDmg(artifact.dmgPath, artifact.executableArch)) {
      failures.push(artifact.dmgPath);
    }
  });

  if (failures.length > 0) {
    console.error(`\nNotarization validation failed for ${failures.length} current release artifact(s).`);
    process.exit(1);
  }
}

main();
