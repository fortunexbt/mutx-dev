const {
  getReleaseArtifacts,
  verifyAppArtifact,
  verifyDmgArtifact,
  verifyZipArtifact,
} = require("./release-artifact-utils");

function fail(message, code = 1) {
  console.error(message);
  process.exit(code);
}

function main() {
  const artifactMode = process.env.MUTX_RELEASE_ARTIFACT_MODE || "built";
  const requestedArch = process.env.MUTX_RELEASE_ARCH;
  const expectedTeamId = process.env.MUTX_EXPECTED_TEAM_ID;
  const requireSignatureIdentity = process.env.MUTX_REQUIRE_SIGNATURE_IDENTITY === "1";
  if (!new Set(["built", "downloaded"]).has(artifactMode)) {
    fail(`Unsupported MUTX_RELEASE_ARTIFACT_MODE: ${artifactMode}`);
  }
  if (requireSignatureIdentity && !expectedTeamId) {
    fail("MUTX_EXPECTED_TEAM_ID is required for release signature identity verification.");
  }

  const artifacts = getReleaseArtifacts(requestedArch ? [requestedArch] : undefined);
  const failures = [];

  for (const artifact of artifacts) {
    const checks = [
      {
        label: `${artifact.arch} zip`,
        path: artifact.zipPath,
        verify: () =>
          verifyZipArtifact(
            artifact.zipPath,
            undefined,
            expectedTeamId,
            artifact.executableArch,
          ),
      },
      {
        label: `${artifact.arch} dmg`,
        path: artifact.dmgPath,
        verify: () =>
          verifyDmgArtifact(
            artifact.dmgPath,
            undefined,
            expectedTeamId,
            artifact.executableArch,
          ),
      },
    ];
    if (artifactMode === "built") {
      checks.unshift({
        label: `${artifact.arch} app`,
        path: artifact.appPath,
        verify: () =>
          verifyAppArtifact(
            artifact.appPath,
            `${artifact.arch} app`,
            expectedTeamId,
            artifact.executableArch,
          ),
      });
    }

    checks.forEach((check) => {
      try {
        check.verify();
        console.log(`OK   ${check.label}  ${check.path}`);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        failures.push(`FAIL ${check.label}  ${check.path}\n${message}`);
      }
    });
  }

  if (failures.length > 0) {
    fail(failures.join("\n\n"));
  }

  console.log(
    `All ${artifactMode} release desktop artifacts passed signature and integrity verification.`,
  );
}

main();
