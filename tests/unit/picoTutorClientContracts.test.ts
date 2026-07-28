import { readFileSync } from 'node:fs'
import { join } from 'node:path'

describe('Pico Tutor client interaction contract', () => {
  const source = readFileSync(
    join(process.cwd(), 'components/pico/PicoTutorPageClient.tsx'),
    'utf8',
  )

  it('canonically reloads both provider mutations before claiming state', () => {
    expect(source.match(/const canonical = await loadConnection\(\)/g)).toHaveLength(2)
    expect(source).toContain("canonical?.status !== 'connected'")
    expect(source).toContain("canonical.status === 'connected'")
    expect(source).not.toContain('setOpenAIConnection(payload as')
  })

  it('binds chat, provider reads, and mutations to abortable stale-response guards', () => {
    expect(source).toContain('const chatRequests = useRef(new LatestTutorRequest())')
    expect(source).toContain('const connectionReads = useRef(new LatestTutorRequest())')
    expect(source).toContain('const connectionMutations = useRef(new LatestTutorRequest())')
    expect(source).toContain('if (!chatRequests.current.isCurrent(lease)) return')
    expect(source).toContain('signal: lease.signal')
  })

  it('keeps accessible read-only guidance and keyboard cancellation on the page', () => {
    expect(source).toContain('data-testid="pico-tutor-academy-guidance"')
    expect(source).toContain('role="alert"')
    expect(source).toContain("event.key === 'Escape'")
    expect(source).toContain('event.currentTarget.form?.requestSubmit()')
    expect(source).toContain("t('form.cancelRequest')")
  })
})
