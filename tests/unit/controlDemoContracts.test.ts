import { readFileSync } from 'node:fs'
import { join } from 'node:path'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

describe('control demo interaction contracts', () => {
  const appSource = readSource('components/dashboard/demo/MutxDemoApp.tsx')
  const primitivesSource = readSource('components/dashboard/demo/demoPrimitives.tsx')
  const contentSource = readSource('components/dashboard/demo/demoContent.ts')
  const sectionsSource = readSource('components/dashboard/demo/routeSections.tsx')
  const boundarySource = [
    readSource('app/control/loading.tsx'),
    readSource('app/control/error.tsx'),
    readSource('app/control/not-found.tsx'),
  ].join('\n')
  const visualSource = [appSource, primitivesSource, contentSource, sectionsSource, boundarySource].join('\n')

  it('uses the shared carbon, bone, and orange flight-recorder grammar', () => {
    expect(appSource).toContain('data-control-visual-system="flight-recorder"')
    expect(visualSource).toContain('#090a08')
    expect(visualSource).toContain('#eee9dc')
    expect(visualSource).toContain('#ff571c')
    expect(visualSource).not.toMatch(/cyan-/)
    expect(visualSource).not.toMatch(/rounded-\[(?:9|1\d|2\d)px\]/)
    expect(visualSource).not.toMatch(/text-\[(?:8|9|10)px\]/)
    expect(visualSource).not.toContain('group-hover:translate')
  })

  it('keeps the demo explicitly simulated and reduced-motion aware', () => {
    expect(appSource).toContain('useReducedMotion() ?? false')
    expect(appSource).toContain('if (prefersReducedMotion)')
    expect(appSource).toContain('data-motion={prefersReducedMotion ? "reduced" : "full"}')
    expect(appSource).toContain('data-no-live-writes="true"')
    expect(appSource).toContain('Simulated interactive demo · sample data · actions stay local')
    expect(primitivesSource).toContain('No live system was changed.')
    expect(visualSource).not.toMatch(/(?:^|[\s"'`])animate-(?:pulse|spin|bounce)/m)
    expect(boundarySource).toContain('motion-reduce:animate-none')
  })

  it('keeps the talk track behind an accessible, focus-managed presenter mode', () => {
    expect(appSource).toContain('const [presenterOpen, setPresenterOpen] = useState(false)')
    expect(appSource).toContain('role="dialog"')
    expect(appSource).toContain('aria-modal="true"')
    expect(appSource).toContain('aria-expanded={presenterOpen}')
    expect(appSource).toContain('setAttribute("inert", "")')
    expect(appSource).toContain('event.key === "Escape"')
    expect(appSource).toContain('presenterTriggerRef.current)?.focus')
    expect(appSource).toContain('presenterOpen ? (')
    expect(appSource).toContain('Demo Script · talk track')
  })

  it('keeps search, local interventions, and settings honest and keyboard operable', () => {
    expect(appSource).toContain('aria-label="Open simulated settings"')
    expect(primitivesSource).toContain('aria-label="Search simulated control plane"')
    expect(primitivesSource).toContain('event.key === "Escape"')
    expect(primitivesSource).toContain('href={item.href}')
    expect(primitivesSource).toContain('onClick={() => setSimulated(true)}')
    expect(sectionsSource).toContain('Write controls unavailable')
    expect(sectionsSource).not.toContain('<button')
  })
})
