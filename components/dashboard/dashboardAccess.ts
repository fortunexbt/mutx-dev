import { extractApiErrorMessage } from '@/components/app/http'
import { canonicalizeDashboardNextPath } from '@/lib/dashboardPanels'
import type { CurrentUser } from '@/lib/store'

export const DASHBOARD_ACCESS_ROUTE = '/api/dashboard/access'

type Fetcher = (input: string | URL | Request, init?: RequestInit) => Promise<Response>

type AccessReason = 'missing_session' | 'expired_session' | 'access_denied'

export type DashboardAccessResult =
  | { authenticated: true; user: CurrentUser }
  | { authenticated: false; reason: AccessReason }

export class DashboardAccessError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'DashboardAccessError'
    this.status = status
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function mapDashboardUser(payload: unknown): CurrentUser | null {
  if (!isRecord(payload)) return null

  const id = typeof payload.id === 'string' ? payload.id : null
  const email = typeof payload.email === 'string' ? payload.email : undefined
  const name =
    typeof payload.name === 'string'
      ? payload.name
      : typeof payload.display_name === 'string'
        ? payload.display_name
        : email?.split('@')[0] || 'Operator'
  const explicitRole =
    payload.role === 'admin' || payload.role === 'operator' || payload.role === 'viewer'
      ? payload.role
      : null
  const roles = Array.isArray(payload.roles)
    ? payload.roles.filter((role): role is string => typeof role === 'string').map((role) => role.toUpperCase())
    : []
  const role = explicitRole
    ?? (roles.includes('ADMIN')
      ? 'admin'
      : roles.includes('DEVELOPER') || roles.includes('OPERATOR')
        ? 'operator'
        : 'viewer')

  if (!id) return null

  return {
    id,
    email,
    username: email?.split('@')[0] || name.toLowerCase().replace(/\s+/g, '-'),
    display_name: name,
    role,
  }
}

export async function resolveDashboardAccess(
  fetcher: Fetcher = fetch,
  signal?: AbortSignal,
): Promise<DashboardAccessResult> {
  const response = await fetcher(DASHBOARD_ACCESS_ROUTE, {
    cache: 'no-store',
    signal,
  })
  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    throw new DashboardAccessError(
      extractApiErrorMessage(payload, 'Dashboard access could not be verified.'),
      response.status,
    )
  }

  if (!isRecord(payload) || typeof payload.authenticated !== 'boolean') {
    throw new DashboardAccessError('Dashboard access returned an invalid response.', 502)
  }

  if (!payload.authenticated) {
    const reason = payload.reason
    if (reason !== 'missing_session' && reason !== 'expired_session' && reason !== 'access_denied') {
      throw new DashboardAccessError('Dashboard access returned an invalid response.', 502)
    }
    return { authenticated: false, reason }
  }

  const user = mapDashboardUser(payload.user)
  if (!user) {
    throw new DashboardAccessError('Dashboard access did not identify an operator.', 502)
  }

  return { authenticated: true, user }
}

export function getDashboardAccessLinks(nextPath: string) {
  const safeNextPath = canonicalizeDashboardNextPath(nextPath)
  const encodedNextPath = encodeURIComponent(safeNextPath)

  return {
    login: `/login?next=${encodedNextPath}`,
    register: `/register?next=${encodedNextPath}`,
    recovery: `/forgot-password?next=${encodedNextPath}`,
  }
}
