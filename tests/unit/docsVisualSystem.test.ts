import { readFileSync } from 'node:fs'
import { join } from 'node:path'

function source(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

describe('documentation visual system', () => {
  const css = source('app/docs/docs.css')

  it('has one scoped base rule for each structural docs surface', () => {
    for (const selector of [
      '.docs-shell',
      '.docs-header',
      '.docs-sidebar',
      '.docs-content',
      '.docs-prose',
      '.docs-toc',
      '.docs-search-trigger',
      '.docs-search-input',
    ]) {
      expect(css.match(new RegExp(`^${selector.replace('.', '\\.')} \\{`, 'gm'))).toHaveLength(1)
    }

    expect(css).not.toContain('GitBook Dark Theme')
    expect(css).not.toContain('Unified public documentation surface')
    expect(css).not.toContain('MUTX public system:')
  })

  it('keeps wide markdown content local to its own scroll container', () => {
    expect(css).toMatch(/\.docs-prose pre\s*\{[\s\S]*?max-inline-size: 100%;[\s\S]*?overflow: auto;/)
    expect(css).toMatch(/\.docs-prose table\s*\{[\s\S]*?max-inline-size: 100%;[\s\S]*?overflow: auto;/)
    expect(css).toMatch(/\.docs-article-main\s*\{[\s\S]*?min-inline-size: 0;/)
    expect(css).not.toMatch(/overflow-x:\s*hidden/)
  })

  it('defines responsive navigation, focus, reduced motion, and RTL geometry', () => {
    expect(css).toContain('@media (max-width: 1023px)')
    expect(css).toContain('@media (max-width: 767px)')
    expect(css).toContain('@media (max-width: 359px)')
    expect(css).toContain(':focus-visible')
    expect(css).toContain('@media (prefers-reduced-motion: reduce)')
    expect(css).toContain('[dir="rtl"] .docs-mobile-sidebar')
    expect(css).toContain('inset-inline-start: 0')
    expect(css).toContain('padding-inline-start')
    expect(css).not.toMatch(/(?:margin|padding|border)-(?:left|right):/)
  })

  it('keeps navigation and section links semantically precise', () => {
    const layout = source('components/site/docs/DocsLayout.tsx')
    const toc = source('components/site/docs/TableOfContents.tsx')
    const renderer = source('components/site/docs/DocsRenderer.tsx')

    expect(layout).toContain("aria-current={isCurrent ? 'page' : undefined}")
    expect(layout).toContain('aria-controls="docs-mobile-navigation"')
    expect(layout).toContain('aria-label={`${open ? \'Collapse\' : \'Expand\'} ${item.title}`}')
    expect(layout).not.toContain('paddingInlineStart:')
    expect(toc).toContain('aria-labelledby="docs-toc-title"')
    expect(toc).toContain("aria-current={activeId === heading.domId ? 'location' : undefined}")
    expect(toc).toContain('domId: h.id')
    expect(renderer).toContain('ariaLabel: "Link to this section"')
    expect(renderer).toContain('const slugCounts = new Map<string, number>()')
  })
})
