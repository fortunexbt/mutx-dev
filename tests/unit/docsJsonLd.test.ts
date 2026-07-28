import fs from 'fs'
import path from 'path'

import { serializeJsonLd } from '../../lib/docs/jsonLd'

describe('documentation JSON-LD serialization', () => {
  it('escapes script-breaking and HTML-significant characters without changing values', () => {
    const fixture = {
      title: '</script><script>globalThis.compromised = true</script>',
      description: 'left\u2028middle\u2029right',
      htmlSignificant: '<tag attr="value">A & B</tag>',
      nested: ['safe', { exact: true }],
    }

    const serialized = serializeJsonLd(fixture)

    expect(serialized).not.toMatch(/<\/script/i)
    expect(serialized).not.toContain('<')
    expect(serialized).not.toContain('>')
    expect(serialized).not.toContain('&')
    expect(serialized).not.toContain('\u2028')
    expect(serialized).not.toContain('\u2029')
    expect(serialized).toContain('\\u003c/script\\u003e')
    expect(serialized).toContain('\\u2028')
    expect(serialized).toContain('\\u2029')
    expect(JSON.parse(serialized)).toEqual(fixture)
  })

  it('is the serializer used by every documentation JSON-LD surface', () => {
    const surfaces = [
      'app/docs/[[...slug]]/page.tsx',
      'app/sdk/page.tsx',
      'app/support/page.tsx',
    ]

    for (const surface of surfaces) {
      const source = fs.readFileSync(path.join(process.cwd(), surface), 'utf-8')
      expect(source).toContain('serializeJsonLd(')
      expect(source).not.toContain('__html: JSON.stringify(')
    }
  })
})
