import { readFileSync } from 'node:fs'
import { join } from 'node:path'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

function contrastRatio(foreground: string, background: string) {
  function luminance(hex: string) {
    const channels = hex
      .replace('#', '')
      .match(/.{2}/g)!
      .map((channel) => parseInt(channel, 16) / 255)
      .map((channel) =>
        channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
      )

    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
  }

  const foregroundLuminance = luminance(foreground)
  const backgroundLuminance = luminance(background)
  return (
    (Math.max(foregroundLuminance, backgroundLuminance) + 0.05) /
    (Math.min(foregroundLuminance, backgroundLuminance) + 0.05)
  )
}

describe('public accessibility style contracts', () => {
  it('keeps docs search text and the header trigger on contrasting theme tokens', () => {
    const css = readSource('app/docs/docs.css')

    expect(css).toMatch(/\.docs-search-input\s*\{[\s\S]*?color:\s*var\(--gb-text\)/)
    expect(css).toMatch(/\.docs-search-result-title\s*\{[\s\S]*?color:\s*var\(--gb-text\)/)
    expect(css).toMatch(/\.docs-search-trigger\s*\{[\s\S]*?background:\s*#171713;[\s\S]*?color:\s*#f3f0e8;/)
    expect(css).toContain('.docs-search-trigger-text { color: inherit; }')
    expect(contrastRatio('#0a0a09', '#f3f0e8')).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio('#f3f0e8', '#171713')).toBeGreaterThanOrEqual(4.5)
  })

  it('keeps docs search modal isolation and scroll restoration in place', () => {
    const source = readSource('components/site/docs/DocsSearch.tsx')

    expect(source).toContain('createPortal(')
    expect(source).toContain('element.inert = true')
    expect(source).toContain("element.setAttribute('aria-hidden', 'true')")
    expect(source).toContain("document.body.style.position = 'fixed'")
    expect(source).toContain("document.documentElement.style.overflow = 'hidden'")
    expect(source).toContain('window.scrollTo(scrollX, scrollY)')
    expect(source).toContain("e.key === 'Escape'")
    expect(source).toContain("e.key !== 'Tab'")
  })

  it('keeps release metadata and the Pico auth divider above contrast thresholds', () => {
    const marketingCss = readSource('components/site/marketing/MarketingCore.module.css')
    const picoAuthSource = readSource('components/pico/PicoAuthPage.tsx')

    expect(marketingCss).toMatch(/\.routeHeroPanel,[\s\S]*?\.routeArtifactPanel\s*\{[\s\S]*?--marketing-text-muted:\s*#5f5b53;/)
    expect(picoAuthSource).toContain('data-auth-divider="pico"')
    expect(picoAuthSource.match(/data-auth-divider-line/g)).toHaveLength(2)
    expect(picoAuthSource).toContain("dividerText: '#a7a39b'")
    expect(picoAuthSource).toContain("dividerLine: '#6d6a63'")
    expect(contrastRatio('#5f5b53', '#f3f0e8')).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio('#a7a39b', '#11110f')).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio('#6d6a63', '#11110f')).toBeGreaterThanOrEqual(3)
  })
})
