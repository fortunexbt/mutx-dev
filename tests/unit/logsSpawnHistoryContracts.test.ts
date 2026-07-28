import { readFileSync } from 'node:fs'
import { join } from 'node:path'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

describe('logs, spawn, and history workflow contracts', () => {
  it('renders generated run details and traces without inventing step data', () => {
    const source = readSource('components/dashboard/LogsPageClient.tsx')

    expect(source).toContain('components["schemas"]["RunDetailResponse"]')
    expect(source).toContain('components["schemas"]["RunTraceResponse"]')
    expect(source).toContain('selectedRun.agent_id || "Unassigned"')
    expect(source).toContain('selectedRun.traces.map((trace)')
    expect(source).toContain('selectedRun.error_message')
    expect(source).not.toContain('interface RunStep')
    expect(source).not.toContain('selectedRun.steps')
  })

  it('turns the history route into a live run activity surface', () => {
    const source = readSource('app/dashboard/history/page.tsx')

    expect(source).toContain('browserView=')
    expect(source).toContain('<LogsPageClient mode="history" />')
    expect(source).not.toContain('browserRedirectTo="/dashboard/monitoring"')
  })

  it('carries the spawn intent into the agent creation dialog', () => {
    const spawnSource = readSource('app/dashboard/spawn/page.tsx')
    const agentsSource = readSource('components/app/AgentsPageClient.tsx')

    expect(spawnSource).toContain('browserRedirectTo="/dashboard/agents?create=1"')
    expect(agentsSource).toContain('searchParams.get("create") === "1"')
    expect(agentsSource).toContain('setIsCreateModalOpen(true)')
    expect(agentsSource).toContain('url.searchParams.delete("create")')
  })
})
