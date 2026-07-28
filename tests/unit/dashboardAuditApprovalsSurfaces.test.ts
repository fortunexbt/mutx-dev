import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import {
  formatOperatorContext,
  redactOperatorContext,
  safeOperatorFileSegment,
} from '../../components/dashboard/operatorContext'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

describe('audit and approvals operator surfaces', () => {
  it('redacts sensitive nested values while preserving attributable context', () => {
    const redacted = redactOperatorContext({
      session_id: 'session-123',
      actor: { id: 'operator-1', access_token: 'never-render-this' },
      payload: { authorization: 'Bearer secret', command: 'deploy' },
    })
    const formatted = formatOperatorContext(redacted)

    expect(formatted).toContain('session-123')
    expect(formatted).toContain('operator-1')
    expect(formatted).toContain('deploy')
    expect(formatted).toContain('[redacted]')
    expect(formatted).not.toContain('never-render-this')
    expect(formatted).not.toContain('Bearer secret')
    expect(safeOperatorFileSegment('../../run one / secrets')).toBe('run-one-secrets')
  })

  it('keeps audit states, pagination, safe detail, and scoped export in the client contract', () => {
    const source = readSource('components/dashboard/AuditPageClient.tsx')

    expect(source).toContain('/api/dashboard/audit/events?')
    expect(source).toContain('PAGE_SIZE + 1')
    expect(source).toContain('loadError.status === 401')
    expect(source).toContain('loadError.status === 403')
    expect(source).toContain('No matching audit events')
    expect(source).toContain('DashboardDialog')
    expect(source).toContain('formatOperatorContext(selectedEvent.payload)')
    expect(source).toContain('Boolean(runId) === Boolean(sessionId)')
    expect(source).toContain('/api/dashboard/audit/export?')
    expect(source).toContain('disabled={!exportContext || exporting}')
    expect(source).not.toContain('dangerouslySetInnerHTML')
  })

  it('keeps canonical approval filtering, decisions, and conflict feedback in the client contract', () => {
    const source = readSource('components/dashboard/ApprovalsPageClient.tsx')

    expect(source).toContain('/api/dashboard/approvals?')
    expect(source).toContain('response.items')
    expect(source).toContain('response.total')
    expect(source).toContain('statusFilter')
    expect(source).toContain('setSkip((value) => value + PAGE_SIZE)')
    expect(source).toContain('Requested by')
    expect(source).toContain('formatOperatorContext(selectedApproval.payload)')
    expect(source).toContain('/${decision}`')
    expect(source).toContain('await reloadCanonicalEnvelope(selectedId)')
    expect(source).toContain('decisionError.status === 403')
    expect(source).toContain('decisionError.status === 400 || decisionError.status === 409')
    expect(source).toContain('role="alert"')
    expect(source).toContain('DashboardDialog')
    expect(source).not.toContain('dangerouslySetInnerHTML')
  })

  it('mounts dedicated browser pages without changing desktop route ownership', () => {
    const auditPage = readSource('app/dashboard/audit/page.tsx')
    const approvalsPage = readSource('app/dashboard/approvals/page.tsx')

    expect(auditPage).toContain('<AuditPageClient />')
    expect(auditPage).toContain('/v1/audit/events')
    expect(approvalsPage).toContain('<ApprovalsPageClient />')
    expect(approvalsPage).toContain('/v1/approvals')
    expect(auditPage).toContain('DesktopRouteBoundary')
    expect(auditPage).toContain('routeKey="audit"')
    expect(approvalsPage).toContain('DesktopRouteBoundary')
    expect(approvalsPage).toContain('routeKey="approvals"')
  })
})
