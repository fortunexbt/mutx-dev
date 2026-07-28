import { ApiRequestError } from '@/components/app/http'

export type DashboardRequestAccessFailure = 'authentication' | 'permission' | null

export function getDashboardRequestAccessFailure(
  error: unknown,
): DashboardRequestAccessFailure {
  if (!(error instanceof ApiRequestError)) return null
  if (error.status === 401) return 'authentication'
  if (error.status === 403) return 'permission'
  return null
}

export function dashboardRequestErrorMessage(error: unknown, fallback: string): string {
  const detail = error instanceof Error && error.message.trim() ? error.message.trim() : fallback

  if (getDashboardRequestAccessFailure(error) === 'permission') {
    return `Permission denied: ${detail}`
  }

  if (getDashboardRequestAccessFailure(error) === 'authentication') {
    return `Authentication required: ${detail}`
  }

  return detail
}
