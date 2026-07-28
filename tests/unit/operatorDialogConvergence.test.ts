import { readFileSync } from 'node:fs'
import { join } from 'node:path'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

const ownedClients = [
  'components/webhooks/WebhooksPageClient.tsx',
  'components/app/AgentsPageClient.tsx',
  'components/app/DeploymentsPageClient.tsx',
  'components/dashboard/SessionsPageClient.tsx',
  'components/dashboard/MonitoringPageClient.tsx',
  'components/dashboard/SwarmsPageClient.tsx',
] as const

const nativeDialogCall = /\b(?:window\.)?(?:confirm|alert)\s*\(/

describe('live operator dialog convergence', () => {
  it.each(ownedClients)('removes native browser dialogs from %s', (path) => {
    expect(readSource(path)).not.toMatch(nativeDialogCall)
  })

  it.each(ownedClients)('uses the shared accessible dialog with pending and mobile/RTL contracts in %s', (path) => {
    const source = readSource(path)

    expect(source).toContain('DashboardDialog')
    expect(source).toContain('<DashboardDialog')
    expect(source).toContain('data-autofocus')
    expect(source).toContain('aria-busy')
    expect(source).toContain('disabled=')
    expect(source).toContain('min-h-11')
    expect(source).toContain('text-start')
  })

  it('confirms webhook deletion with its URL and ID and refreshes delivery truth after tests', () => {
    const source = readSource('components/webhooks/WebhooksPageClient.tsx')

    expect(source).toContain('title="Delete webhook"')
    expect(source).toContain('deleteTarget?.url')
    expect(source).toContain('deleteTarget?.id')
    expect(source).toContain('"Delete Webhook"')
    expect(source).toContain('Webhook deletion failed: {deleteError}')
    expect(source).toContain('if (!deleteTarget || deletingId) return')
    expect(source).toContain('await hydrateDeliverySignals(webhooks)')
    expect(source).toContain('message: response.message || "Test event delivered successfully."')
    expect(source).toContain('role="status"')
    expect(source).toContain('aria-live="polite"')
  })

  it('confirms agent stop and delete against the named fleet record', () => {
    const source = readSource('components/app/AgentsPageClient.tsx')

    expect(source).toContain('kind: "stop" | "delete"')
    expect(source).toContain('pendingAction?.agent.name')
    expect(source).toContain('pendingAction?.agent.id')
    expect(source).toContain('"Stop Agent"')
    expect(source).toContain('"Delete Agent"')
    expect(source).toContain('if (!pendingAction || deletingId || stoppingId) return')
    expect(source).toContain('Agent deletion')
    expect(source).toContain('Agent stop')
  })

  it('confirms irreversible deployment termination without changing the request semantics', () => {
    const source = readSource('components/app/DeploymentsPageClient.tsx')

    expect(source).toContain('title="Terminate deployment"')
    expect(source).toContain('terminationTarget?.id')
    expect(source).toContain('terminationTarget?.agent_id')
    expect(source).toContain('"Terminate Deployment"')
    expect(source).toContain('cannot be restarted after termination')
    expect(source).toContain('method: "DELETE"')
    expect(source).toContain('if (!terminationTarget || processingIds.has(terminationTarget.id)) return')
  })

  it('confirms every gateway session lifecycle action with action-specific consequences', () => {
    const source = readSource('components/dashboard/SessionsPageClient.tsx')

    expect(source).toContain('type SessionOperatorAction = SessionControlAction | "delete"')
    expect(source).toContain('requestSessionAction(session, session.active ? "pause" : "resume")')
    expect(source).toContain('requestSessionAction(session, "kill")')
    expect(source).toContain('requestSessionAction(session, "delete")')
    expect(source).toContain('A terminated session cannot be resumed.')
    expect(source).toContain('gateway session and its history will be removed')
    expect(source).toContain('pendingAction?.session.key')
    expect(source).toContain('if (!pendingAction || actingKey) return')
    expect(source).toContain('Session action failed: {dialogError}')
  })

  it('confirms alert resolve/reopen while distinguishing workflow state from remediation', () => {
    const source = readSource('components/dashboard/MonitoringPageClient.tsx')

    expect(source).toContain('setPendingAction({ alert, resolved })')
    expect(source).toContain('pendingAction?.alert.id')
    expect(source).toContain('pendingAction?.alert.agent_id')
    expect(source).toContain('`${pendingVerb} Alert`')
    expect(source).toContain('it does not remediate the underlying condition')
    expect(source).toContain('body: JSON.stringify({ resolved })')
    expect(source).toContain('Alert action failed: {dialogError}')
  })

  it('confirms swarm-wide scaling and grouping deletion with distinct consequences', () => {
    const source = readSource('components/dashboard/SwarmsPageClient.tsx')

    expect(source).toContain("{ kind: 'scale'; swarm: Swarm; replicas: number }")
    expect(source).toContain("{ kind: 'delete'; swarm: Swarm }")
    expect(source).toContain("pendingAction?.swarm.name")
    expect(source).toContain("pendingAction?.swarm.id")
    expect(source).toContain("'Delete Swarm'")
    expect(source).toContain("'Scale Swarm'")
    expect(source).toContain('Every active deployment in this swarm will be scaled')
    expect(source).toContain('Its agents and deployments will remain available outside this group')
    expect(source).toContain('body: JSON.stringify({ replicas: action.replicas })')
    expect(source).toContain("{ method: 'DELETE' }")
    expect(source).toContain('if (!pendingAction || actingId) return')
  })

  it('inherits focus trap and focus return behavior from the shared DashboardDialog', () => {
    const source = readSource('components/dashboard/DashboardDialog.tsx')

    expect(source).toContain('if (event.key !== "Tab"')
    expect(source).toContain('document.addEventListener("focusin", handleFocusIn)')
    expect(source).toContain('returnFocus.focus({ preventScroll: true })')
    expect(source).toContain('aria-modal="true"')
  })
})
