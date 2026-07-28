import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import {
  deploymentAllowsAction,
  deploymentErrorMessage,
  type DeploymentAction,
  type DeploymentActionCapabilities,
} from '../../components/app/DeploymentsPageClient'
import { ApiRequestError } from '../../components/app/http'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

function deploymentWithActions(
  allowedActions?: readonly DeploymentAction[],
): DeploymentActionCapabilities {
  return allowedActions ? { allowed_actions: allowedActions } : {}
}

describe('deployment lifecycle UI contracts', () => {
  it('uses backend capabilities as a fail-closed action state machine', () => {
    const running = deploymentWithActions(['stop', 'restart', 'scale', 'terminate'])
    const stopped = deploymentWithActions(['start', 'terminate'])

    expect(deploymentAllowsAction(running, 'restart')).toBe(true)
    expect(deploymentAllowsAction(running, 'start')).toBe(false)
    expect(deploymentAllowsAction(stopped, 'start')).toBe(true)
    expect(deploymentAllowsAction(stopped, 'scale')).toBe(false)
    expect(deploymentAllowsAction(deploymentWithActions(), 'terminate')).toBe(false)
  })

  it('keeps authentication, authorization, absence, and server failures distinct', () => {
    expect(deploymentErrorMessage(new ApiRequestError('unauthorized', 401), 'fallback')).toContain(
      'session expired',
    )
    expect(deploymentErrorMessage(new ApiRequestError('forbidden', 403), 'fallback')).toContain(
      'permission',
    )
    expect(deploymentErrorMessage(new ApiRequestError('missing', 404), 'fallback')).toContain(
      'no longer exists',
    )
    expect(deploymentErrorMessage(new ApiRequestError('upstream', 503), 'Retry later.')).toContain(
      'control plane',
    )
  })

  it('reloads canonical deployment detail after every successful non-terminal mutation', () => {
    const source = readSource('app/dashboard/deployments/[id]/page.tsx')

    expect(source).toContain('writeJson<unknown>')
    expect(source).not.toContain('const payload = await writeJson<Deployment>')
    expect(source.match(/await loadDeployment\(\{ preserveLoading: true \}\);/g)?.length).toBeGreaterThanOrEqual(5)
    expect(source).toContain('deploymentAllowsAction(deployment, "start")')
    expect(source).toContain('deploymentAllowsAction(deployment, "stop")')
    expect(source).toContain('deploymentAllowsAction(deployment, "restart")')
    expect(source).toContain('deploymentAllowsAction(deployment, "scale")')
    expect(source).toContain('deploymentAllowsAction(deployment, "terminate")')
    expect(source).toContain('role="alert"')
  })

  it('reloads the deployment registry after list mutations and capability-gates controls', () => {
    const source = readSource('components/app/DeploymentsPageClient.tsx')

    expect(source).toContain('writeJson<unknown>')
    expect(source.match(/await loadDeployments\(\);/g)?.length).toBeGreaterThanOrEqual(5)
    expect(source).toContain('deploymentAllowsAction(deployment, "start")')
    expect(source).toContain('deploymentAllowsAction(deployment, "stop")')
    expect(source).toContain('deploymentAllowsAction(deployment, "restart")')
    expect(source).toContain('deploymentAllowsAction(deployment, "terminate")')
  })
})

describe('agent lifecycle detail contracts', () => {
  it('uses the full detail type and canonical refetch after subset action responses', () => {
    const source = readSource('app/dashboard/agents/[agentId]/page.tsx')

    expect(source).toContain('type Agent = components["schemas"]["AgentDetailResponse"]')
    expect(source).toContain('writeJson<unknown>')
    expect(source).not.toContain('writeJson<Agent>')
    expect(source.match(/await loadAgent\(\{ preserveLoading: true \}\);/g)?.length).toBeGreaterThanOrEqual(3)
    expect(source).toContain('loadError.status === 401')
    expect(source).toContain('loadError.status === 403')
    expect(source).toContain('loadError.status === 404')
    expect(source).toContain('loadError.status >= 500')
    expect(source).toContain('if (status === "creating") return action === "delete"')
    expect(source).toContain('role="alert"')
  })
})
