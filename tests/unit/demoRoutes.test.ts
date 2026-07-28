import {
  DEMO_SECTIONS,
  getDemoSectionHref,
  isDemoSection,
} from '../../components/dashboard/demo/demoSections'
import { NAV_ITEMS, SECTION_META } from '../../components/dashboard/demo/demoContent'

describe('demo dashboard routes', () => {
  it('keeps every demo section inside the public /control sandbox', () => {
    const hrefs = NAV_ITEMS.map((item) => item.href)

    expect(hrefs).toEqual([
      '/control',
      '/control/agents',
      '/control/deployments',
      '/control/runs',
      '/control/environments',
      '/control/access',
      '/control/connectors',
      '/control/audit',
      '/control/usage',
      '/control/settings',
    ])

    expect(hrefs.every((href) => href === '/control' || href.startsWith('/control/'))).toBe(true)
    expect(new Set(hrefs).size).toBe(hrefs.length)
    expect(NAV_ITEMS.map((item) => item.key)).toEqual(DEMO_SECTIONS)
  })

  it('builds stable control hrefs for known demo sections', () => {
    expect(getDemoSectionHref('overview')).toBe('/control')
    expect(getDemoSectionHref('agents')).toBe('/control/agents')
    expect(getDemoSectionHref('settings')).toBe('/control/settings')
  })

  it('recognizes the sections used by the demo app route handler', () => {
    expect(isDemoSection('agents')).toBe(true)
    expect(isDemoSection('settings')).toBe(true)
    expect(isDemoSection('dashboard')).toBe(false)
  })

  it('gives every sample route a presenter narrative without adding another route target', () => {
    for (const section of DEMO_SECTIONS) {
      expect(SECTION_META[section].command).toBeTruthy()
      expect(SECTION_META[section].narrative.length).toBeGreaterThanOrEqual(3)
      expect(getDemoSectionHref(section)).toBe(NAV_ITEMS.find((item) => item.key === section)?.href)
    }
  })
})
