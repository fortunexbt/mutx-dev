const {
  archDefinitions,
  parseExecutableArchitectures,
} = jest.requireActual('../../desktop/scripts/release-artifact-utils.js')
const {
  requiredSharpPackages,
} = jest.requireActual('../../desktop/scripts/prepare-standalone-native-deps.js')

describe('desktop release artifact architecture contract', () => {
  it('maps public architecture labels to exact Mach-O architecture names', () => {
    expect(archDefinitions).toMatchObject({
      arm64: { arch: 'arm64', executableArch: 'arm64' },
      x64: { arch: 'x64', executableArch: 'x86_64' },
    })
    expect(parseExecutableArchitectures('arm64\n')).toEqual(['arm64'])
    expect(parseExecutableArchitectures('x86_64 arm64\n')).toEqual(['x86_64', 'arm64'])
  })

  it('derives both locked sharp runtime packages for each packaged architecture', () => {
    const sharpPackage = {
      optionalDependencies: {
        '@img/sharp-darwin-arm64': '1.2.3',
        '@img/sharp-libvips-darwin-arm64': '4.5.6',
        '@img/sharp-darwin-x64': '1.2.3',
        '@img/sharp-libvips-darwin-x64': '4.5.6',
      },
    }

    expect(requiredSharpPackages(sharpPackage, 'arm64')).toEqual([
      { name: '@img/sharp-darwin-arm64', version: '1.2.3' },
      { name: '@img/sharp-libvips-darwin-arm64', version: '4.5.6' },
    ])
    expect(requiredSharpPackages(sharpPackage, 'x64')).toEqual([
      { name: '@img/sharp-darwin-x64', version: '1.2.3' },
      { name: '@img/sharp-libvips-darwin-x64', version: '4.5.6' },
    ])
  })

  it('fails closed when the standalone sharp package omits an architecture dependency', () => {
    expect(() => requiredSharpPackages({ optionalDependencies: {} }, 'x64')).toThrow(
      'Standalone sharp does not declare the required @img/sharp-darwin-x64 dependency.'
    )
  })
})
