import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

function collectCssFiles(relativeDirectory: string): string[] {
  const files: string[] = []
  const directories = [join(process.cwd(), relativeDirectory)]

  while (directories.length) {
    const directory = directories.pop()
    if (!directory) continue

    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name)
      if (entry.isDirectory()) directories.push(path)
      else if (entry.isFile() && entry.name.endsWith('.css')) files.push(path)
    }
  }

  return files
}

describe('Pico RTL, motion, and keyboard contracts', () => {
  it('suppresses Pico animation, transitions, and smooth scrolling for reduced motion', () => {
    const source = readSource('app/pico/pico.css')

    expect(source).toContain('@media (prefers-reduced-motion: reduce)')
    expect(source).toContain('.pico-root *::before')
    expect(source).toContain('scroll-behavior: auto !important')
    expect(source).toContain('animation-duration: 0.01ms !important')
    expect(source).toContain('transition-duration: 0.01ms !important')

    for (const relativePath of [
      'components/pico/PicoForgotPasswordPageClient.tsx',
      'components/pico/PicoResetPasswordPageClient.tsx',
      'components/pico/PicoVerifyEmailPageClient.tsx',
    ]) {
      expect(readSource(relativePath)).not.toMatch(/animate-spin(?![^"']*motion-reduce:animate-none)/)
    }
  })

  it('uses logical inline geometry throughout Pico CSS', () => {
    const physicalInlineGeometry =
      /(?:^|[;{])\s*(?:left|right|margin-left|margin-right|padding-left|padding-right|border-left|border-right)\s*:/m
    const physicalTextAlignment = /text-align:\s*(?:left|right)\s*;/

    for (const path of [
      ...collectCssFiles('app/pico'),
      ...collectCssFiles('components/pico'),
    ]) {
      const source = readFileSync(path, 'utf8')
      expect(source).not.toMatch(physicalInlineGeometry)
      expect(source).not.toMatch(physicalTextAlignment)
    }
  })

  it('mirrors directional action icons and isolates prices and commands', () => {
    for (const relativePath of [
      'components/pico/PicoContactForm.tsx',
      'components/pico/PicoLandingPoster.tsx',
      'components/pico/PicoPricingPage.tsx',
    ]) {
      const source = readSource(relativePath)
      expect(source).not.toMatch(/<ArrowRight(?![^>]*rtl-directional-icon)/)
    }

    expect(readSource('components/pico/PicoLandingPoster.tsx')).toContain('<bdi dir="ltr">')
    expect(readSource('components/pico/PicoPricingPage.tsx')).toContain('<bdi dir="ltr">')
    expect(readSource('components/pico/PicoTutorPageClient.tsx')).toMatch(
      /<pre[^>]+dir="ltr">\s*<code>\{command\.code\}/,
    )
  })

  it('labels and traps the contact dialog while preserving Arabic select direction', () => {
    const source = readSource('components/pico/PicoContactForm.tsx')

    expect(source).toContain("aria-labelledby={titleId}")
    expect(source).toContain("role='dialog'")
    expect(source).toContain("aria-modal='true'")
    expect(source).toContain('getFocusableElements(modalRef.current)')
    expect(source).toContain('previouslyFocused?.focus({ preventScroll: true })')
    expect(source).toContain('dir={getPicoDirection(locale)}')
  })
})
