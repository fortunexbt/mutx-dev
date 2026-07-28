import { readFileSync } from 'node:fs'
import { join } from 'node:path'

describe('desktop release workflow', () => {
  it('publishes only after draft checks and both native architecture launch gates', () => {
    const workflow = readFileSync(
      join(process.cwd(), '.github/workflows/release.yml'),
      'utf8'
    )

    const localCheck = workflow.indexOf('Require complete local desktop artifact set')
    const releaseNotes = workflow.indexOf('Require exact versioned release notes')
    const draftRelease = workflow.indexOf('Create or update draft GitHub release')
    const upload = workflow.indexOf('Upload signed desktop assets')
    const remoteCheck = workflow.indexOf('Verify uploaded desktop artifact set')
    const nativeLaunch = workflow.indexOf('desktop-launch-smoke:')
    const publish = workflow.indexOf('Re-resolve tag binding and publish the native-gated draft')

    expect(localCheck).toBeGreaterThan(-1)
    expect(releaseNotes).toBeGreaterThan(localCheck)
    expect(draftRelease).toBeGreaterThan(releaseNotes)
    expect(upload).toBeGreaterThan(draftRelease)
    expect(remoteCheck).toBeGreaterThan(upload)
    expect(nativeLaunch).toBeGreaterThan(remoteCheck)
    expect(publish).toBeGreaterThan(nativeLaunch)
    expect(workflow).toContain('create_args=(')
    expect(workflow).toContain('--draft\n')
    expect(workflow).toContain('--verify-tag')
    expect(workflow).toContain('gh release create "${create_args[@]}"')
    expect(workflow).toContain('if [[ "${is_draft}" != "true" ]]')
    expect(workflow).toContain('if [[ "${release_is_draft}" != "true" ]]')
    expect(workflow).toContain('--draft=false')
    expect(workflow).toContain('bash scripts/verify-release-tag-binding.sh')
    expect(workflow).toContain('needs.desktop-launch-smoke.result == \'success\'')
    expect(workflow).toContain('Stable release requires non-empty versioned notes')
    expect(workflow).toContain('RELEASE_NOTES_FILE: ${{ steps.release_notes.outputs.path }}')
    expect(workflow.match(/shasum -a 256 -c "\$\{checksum_file\}"/g)).toHaveLength(2)
    expect(workflow).toContain('gh release download "${RELEASE_TAG}" --dir "${remote_dir}"')
    expect(workflow).toContain(
      'cmp -s "dist/desktop/${checksum_file}" "${remote_dir}/${checksum_file}"'
    )

    for (const suffix of [
      'macos-arm64.dmg',
      'macos-x64.dmg',
      'macos-arm64.zip',
      'macos-x64.zip',
      'SHA256SUMS.txt',
    ]) {
      expect(workflow).toContain(`MUTX-\${VERSION}-${suffix}`)
    }
  })

  it('requires explicit confirmation for manual stable promotion while preserving tag promotion', () => {
    const workflow = readFileSync(
      join(process.cwd(), '.github/workflows/release.yml'),
      'utf8'
    )

    expect(workflow).toContain('confirm_production:')
    expect(workflow).toContain('promote_existing')
    expect(workflow).toContain('expected_confirmation="PROMOTE ${RELEASE_TAG}"')
    expect(workflow).toContain("github.event_name == 'workflow_dispatch'")
    expect(workflow).toContain("github.event_name == 'push'")
    expect(workflow).toContain(
      "inputs.confirm_production == format('PROMOTE {0}', needs.resolve_target.outputs.target_tag)"
    )
  })

  it('verifies both architecture routes and the source-backed checksum contract in production', () => {
    const verifier = readFileSync(
      join(process.cwd(), 'scripts/verify-production-release.sh'),
      'utf8'
    )

    expect(verifier).toContain('${SITE_URL}/docs/releases/v${RELEASE_LINE}')
    expect(verifier).toContain('verify_architecture_download "${ARM64_DOWNLOAD_ROUTE}"')
    expect(verifier).toContain('verify_architecture_download "${INTEL_DOWNLOAD_ROUTE}"')
    expect(verifier).toContain('--range 0-0 "${route}"')
    expect(verifier).toContain('verify_published_artifacts "${GITHUB_RELEASE_DOWNLOAD_URL}"')
    expect(verifier).toContain('verify-checksum-manifest.js')
    expect(verifier).toContain("--proto '=https'")
    expect(verifier).toContain('"MUTX-${RELEASE_VERSION}-macos-arm64.dmg"')
    expect(verifier).toContain('"MUTX-${RELEASE_VERSION}-macos-x64.dmg"')
    expect(verifier).toContain('"MUTX-${RELEASE_VERSION}-macos-arm64.zip"')
    expect(verifier).toContain('"MUTX-${RELEASE_VERSION}-macos-x64.zip"')
  })

  it('locks the supported Electron line and truthful macOS floor', () => {
    const packageJson = JSON.parse(readFileSync(join(process.cwd(), 'package.json'), 'utf8'))
    const packageLock = JSON.parse(
      readFileSync(join(process.cwd(), 'package-lock.json'), 'utf8')
    )

    expect(packageJson.devDependencies.electron).toBe('43.2.0')
    expect(packageJson.build.mac.minimumSystemVersion).toBe('12.0')
    expect(packageLock.packages[''].devDependencies.electron).toBe('43.2.0')
    expect(packageLock.packages['node_modules/electron']).toMatchObject({
      version: '43.2.0',
      resolved: 'https://registry.npmjs.org/electron/-/electron-43.2.0.tgz',
      integrity:
        'sha512-80zvrgG7ZRXD+tD0IyLvrnN9n+veSxadMRsMaC9wKKP3iUbtC7rGM8+dVuCmOb0Rrwwv8ESW4awnUZh9Hbp1fA==',
    })
  })

  it('runs exact staged and recovery artifacts on native arm64 and x64 macOS runners', () => {
    const workflow = readFileSync(
      join(process.cwd(), '.github/workflows/release.yml'),
      'utf8'
    )

    expect(workflow).toContain('runner: macos-26')
    expect(workflow).toContain('runner: macos-26-intel')
    expect(workflow).toContain('gh release verify-asset')
    expect(workflow).toContain('if [[ "$(uname -m)" != "${expected_machine}" ]]')
    expect(workflow).toContain('"$(lipo -archs "${executable}")"')
    expect(workflow).toContain('node desktop/scripts/launch-built-app.js')
    expect(workflow).toContain('MUTX_RELEASE_ARTIFACT_MODE: downloaded')
    expect(workflow).toContain("inputs.operation == 'promote_existing'")
    expect(workflow).toContain('MUTX_EXPECTED_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}')
    expect(workflow).toContain("MUTX_REQUIRE_SIGNATURE_IDENTITY: '1'")
  })

  it('prepares locked standalone native dependencies and verifies every package architecture', () => {
    const packager = readFileSync(
      join(process.cwd(), 'desktop/scripts/package-release.js'),
      'utf8'
    )
    const artifactVerifier = readFileSync(
      join(process.cwd(), 'desktop/scripts/release-artifact-utils.js'),
      'utf8'
    )

    expect(packager.indexOf('prepareStandaloneNativeDependencies(args.archs)')).toBeLessThan(
      packager.indexOf('args.archs.forEach((arch) => buildElectronZip(arch))')
    )
    expect(artifactVerifier).toContain('executableArch: "arm64"')
    expect(artifactVerifier).toContain('executableArch: "x86_64"')
    expect(artifactVerifier).toContain('run("lipo", ["-archs", executablePath])')
    expect(artifactVerifier).toContain('expected exactly ${expectedArch}')
  })

  it('generates checksums from only the exact current-version package set', () => {
    const checksumGenerator = readFileSync(
      join(process.cwd(), 'desktop/scripts/generate-checksums.sh'),
      'utf8'
    )

    for (const suffix of [
      'macos-arm64.dmg',
      'macos-x64.dmg',
      'macos-arm64.zip',
      'macos-x64.zip',
    ]) {
      expect(checksumGenerator).toContain(`"MUTX-\${VERSION}-${suffix}"`)
    }
    expect(checksumGenerator).toContain('! -f "$artifact" || -L "$artifact" || ! -s "$artifact"')
    expect(checksumGenerator).not.toContain('for pattern in *.dmg *.zip')
  })

  it('documents v1.4 desktop binaries as unavailable rather than fabricated', () => {
    const releaseNotes = readFileSync(
      join(process.cwd(), 'docs/releases/v1.4.md'),
      'utf8'
    )
    const checklist = readFileSync(
      join(process.cwd(), 'docs/releases/v1.4-checklist.md'),
      'utf8'
    )

    expect(releaseNotes).toContain('v1.4.0 itself did not publish desktop binaries')
    expect(releaseNotes).toContain('ignores v1.4.0')
    expect(checklist).toContain('v1.4.0 was published without the five-file desktop artifact set')
    expect(checklist).toContain('candidate requirement, not')
  })
})
