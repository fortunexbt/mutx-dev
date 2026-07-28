const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const rootDir = path.resolve(__dirname, "../..");
const standaloneModulesDir = path.join(rootDir, ".next", "standalone", "node_modules");
const rootLockPath = path.join(rootDir, "package-lock.json");

function packagePath(baseDir, packageName) {
  return path.join(baseDir, ...packageName.split("/"));
}

function requiredSharpPackages(sharpPackage, arch) {
  const optionalDependencies = sharpPackage.optionalDependencies || {};
  const packageNames = [
    `@img/sharp-darwin-${arch}`,
    `@img/sharp-libvips-darwin-${arch}`,
  ];

  return packageNames.map((name) => {
    const version = optionalDependencies[name];
    if (typeof version !== "string" || !version) {
      throw new Error(`Standalone sharp does not declare the required ${name} dependency.`);
    }
    return { name, version };
  });
}

function buildLockedInstall(packages) {
  const lock = JSON.parse(fs.readFileSync(rootLockPath, "utf8"));
  const dependencies = Object.fromEntries(
    packages.map(({ name, version }) => [name, version]),
  );
  const lockedPackages = {
    "": {
      name: "mutx-standalone-native-deps",
      version: "0.0.0",
      dependencies,
    },
  };

  for (const dependency of packages) {
    const entry = lock.packages?.[`node_modules/${dependency.name}`];
    if (
      entry?.version !== dependency.version ||
      typeof entry.resolved !== "string" ||
      typeof entry.integrity !== "string"
    ) {
      throw new Error(
        `${dependency.name}@${dependency.version} is not pinned with resolved URL and integrity in package-lock.json.`,
      );
    }
    lockedPackages[`node_modules/${dependency.name}`] = entry;
  }

  return {
    packageJson: {
      name: "mutx-standalone-native-deps",
      version: "0.0.0",
      private: true,
      dependencies,
    },
    packageLock: {
      name: "mutx-standalone-native-deps",
      version: "0.0.0",
      lockfileVersion: 3,
      requires: true,
      packages: lockedPackages,
    },
  };
}

function readInstalledPackage(baseDir, dependency) {
  const manifestPath = path.join(packagePath(baseDir, dependency.name), "package.json");
  if (!fs.existsSync(manifestPath)) {
    return null;
  }

  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  return manifest.version === dependency.version ? manifest : null;
}

function installLockedPackages(packages, arch) {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), `mutx-standalone-${arch}-`));
  try {
    const lockedInstall = buildLockedInstall(packages);
    fs.writeFileSync(
      path.join(tempDir, "package.json"),
      `${JSON.stringify(lockedInstall.packageJson, null, 2)}\n`,
    );
    fs.writeFileSync(
      path.join(tempDir, "package-lock.json"),
      `${JSON.stringify(lockedInstall.packageLock, null, 2)}\n`,
    );

    const result = spawnSync(
      "npm",
      [
        "ci",
        "--ignore-scripts",
        "--include=optional",
        "--no-audit",
        "--no-fund",
        `--cpu=${arch}`,
        "--os=darwin",
      ],
      {
        cwd: tempDir,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
        env: process.env,
      },
    );
    if (result.status !== 0) {
      throw new Error(
        `Could not install locked ${arch} standalone dependencies:\n${result.stdout || ""}${result.stderr || ""}`,
      );
    }

    for (const dependency of packages) {
      const source = packagePath(path.join(tempDir, "node_modules"), dependency.name);
      const target = packagePath(standaloneModulesDir, dependency.name);
      if (!readInstalledPackage(path.join(tempDir, "node_modules"), dependency)) {
        throw new Error(`Installed ${dependency.name} does not match ${dependency.version}.`);
      }
      fs.rmSync(target, { recursive: true, force: true });
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.cpSync(source, target, { recursive: true });
    }
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

function prepareStandaloneNativeDependencies(archs) {
  const sharpManifestPath = path.join(standaloneModulesDir, "sharp", "package.json");
  if (!fs.existsSync(sharpManifestPath)) {
    throw new Error(
      "Standalone sharp runtime not found. Run the production Next.js build before desktop packaging.",
    );
  }

  const sharpPackage = JSON.parse(fs.readFileSync(sharpManifestPath, "utf8"));
  for (const arch of archs) {
    if (!new Set(["arm64", "x64"]).has(arch)) {
      throw new Error(`Unsupported standalone dependency architecture: ${arch}`);
    }

    const packages = requiredSharpPackages(sharpPackage, arch);
    buildLockedInstall(packages);
    const missingPackages = packages.filter(
      (dependency) => !readInstalledPackage(standaloneModulesDir, dependency),
    );
    if (missingPackages.length > 0) {
      console.log(
        `[desktop:package:release] Installing locked ${arch} standalone runtime dependencies.`,
      );
      installLockedPackages(missingPackages, arch);
    }

    for (const dependency of packages) {
      if (!readInstalledPackage(standaloneModulesDir, dependency)) {
        throw new Error(`Standalone runtime is missing ${dependency.name}@${dependency.version}.`);
      }
    }
  }
}

module.exports = {
  prepareStandaloneNativeDependencies,
  requiredSharpPackages,
};
