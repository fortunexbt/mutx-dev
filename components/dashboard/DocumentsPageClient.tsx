'use client'

import Link from 'next/link'
import { useEffect, useMemo, useRef, useState } from 'react'

import {
  ApiRequestError,
  extractApiErrorMessage,
  readJson,
  writeJson,
} from '@/components/app/http'
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from '@/components/dashboard/dashboardRequestAccess'
import {
  LiveAuthRequired,
  LiveEmptyState,
  LiveErrorState,
  LiveForbidden,
  LiveLoading,
  LivePanel,
  LiveStatCard,
  LiveKpiGrid,
  asDashboardStatus,
  formatRelativeTime,
} from '@/components/dashboard/livePrimitives'
import { FeatureHint } from '@/components/dashboard/FeatureHint'
import { StatusBadge } from '@/components/dashboard/StatusBadge'

type DocumentTemplateInput = {
  name: string
  type: string
  required: boolean
  accepts_multiple: boolean
}

export type DocumentTemplate = {
  id: string
  name: string
  summary: string
  description: string
  supports_managed: boolean
  supports_local: boolean
  max_upload_bytes: number
  inputs: DocumentTemplateInput[]
}

type DocumentArtifact = {
  id: string
  role: string
  kind: string
  storage_backend: string
  filename: string
}

type DocumentJob = {
  id: string
  run_id: string
  template_id: string
  execution_mode: string
  status: string
  parameters: Record<string, unknown>
  result_summary: Record<string, unknown>
  error_message?: string | null
  created_at?: string | null
  completed_at?: string | null
  artifacts: DocumentArtifact[]
}

type DocumentJobHistory = {
  items: DocumentJob[]
  total: number
}

type BridgeResult<T> = T & { success?: boolean; error?: string }

type ManagedUpload = {
  role: string
  file: File
}

function isDesktopRuntime() {
  return typeof window !== 'undefined' && Boolean(window.mutxDesktop?.isDesktop)
}

function formatBytes(value: number) {
  return value >= 1024 * 1024
    ? `${Math.floor(value / (1024 * 1024))} MB`
    : `${Math.ceil(value / 1024)} KB`
}

export function validateManagedDocumentSubmission(
  template: DocumentTemplate | null,
  parameters: Record<string, unknown>,
  uploads: ManagedUpload[],
) {
  if (!template) return 'Choose a document workflow template.'
  if (!template.supports_managed) return `${template.name} does not support managed execution.`

  const roles = uploads.map((item) => item.role)
  const missing = template.inputs
    .filter((input) => input.required)
    .filter((input) => {
      if (input.type === 'artifact') return !roles.includes(input.name)
      return !String(parameters[input.name] ?? '').trim()
    })
    .map((input) => input.name)

  if (missing.length > 0) {
    return `Missing required inputs for ${template.name}: ${missing.join(', ')}.`
  }

  const empty = uploads.find((item) => item.file.size === 0)
  if (empty) return `${empty.file.name} is empty. Choose a document with content.`

  const oversized = uploads.find((item) => item.file.size > template.max_upload_bytes)
  if (oversized) {
    return `${oversized.file.name} exceeds the ${formatBytes(template.max_upload_bytes)} per-file limit.`
  }

  return null
}

export function describeDocumentRequestError(error: unknown) {
  if (!(error instanceof ApiRequestError)) {
    return error instanceof Error
      ? `Network error: ${error.message}. No execution was confirmed.`
      : 'Network error while submitting documents. No execution was confirmed.'
  }

  const detail = error.message
  if (error.status === 401) return `Authentication required: ${detail}`
  if (error.status === 403) return `Permission denied: ${detail}`
  if (error.status === 404) return `Document workflow not found: ${detail}`
  if (error.status === 409) return `Submission conflict: ${detail}`
  if (error.status === 413) return `Upload rejected: ${detail}`
  if (error.status === 429) return `Document quota exceeded: ${detail}`
  if (error.status === 503) return `Document service unavailable: ${detail}`
  if (error.status >= 500) {
    return `Document service error: ${detail}. Review canonical history before retrying.`
  }
  return `Document submission rejected: ${detail}`
}

export function DocumentsPageClient() {
  const [loading, setLoading] = useState(true)
  const [authRequired, setAuthRequired] = useState(false)
  const [permissionDenied, setPermissionDenied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [templates, setTemplates] = useState<DocumentTemplate[]>([])
  const [jobs, setJobs] = useState<DocumentJob[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState('document_analysis')
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [managedFiles, setManagedFiles] = useState<File[]>([])
  const [managedBaseFile, setManagedBaseFile] = useState<File | null>(null)
  const [managedComparisonFile, setManagedComparisonFile] = useState<File | null>(null)
  const [instructions, setInstructions] = useState('')
  const [redactionPolicy, setRedactionPolicy] = useState('')
  const [submittingManaged, setSubmittingManaged] = useState(false)
  const [cleaningJobId, setCleaningJobId] = useState<string | null>(null)
  const [desktopFiles, setDesktopFiles] = useState<string[]>([])
  const [desktopBaseFile, setDesktopBaseFile] = useState<string | null>(null)
  const [desktopComparisonFile, setDesktopComparisonFile] = useState<string | null>(null)
  const [desktopBusy, setDesktopBusy] = useState(false)
  const managedSubmissionKeyRef = useRef<string | null>(null)

  const selectedTemplate = useMemo(
    () => templates.find((item) => item.id === selectedTemplateId) ?? null,
    [templates, selectedTemplateId],
  )
  const selectedJob = useMemo(
    () => jobs.find((item) => item.id === selectedJobId) ?? null,
    [jobs, selectedJobId],
  )

  async function loadData(nextJobId?: string) {
    setLoading(true)
    setError(null)
    setAuthRequired(false)
    setPermissionDenied(false)

    try {
      const [templateResponse, jobsResponse] = await Promise.all([
        readJson<DocumentTemplate[]>('/api/dashboard/documents/templates'),
        readJson<DocumentJobHistory>('/api/dashboard/documents/jobs?limit=20'),
      ])
      setTemplates(templateResponse)
      setJobs(jobsResponse.items ?? [])
      setSelectedTemplateId((current) => current || templateResponse[0]?.id || 'document_analysis')
      setSelectedJobId(nextJobId ?? jobsResponse.items?.[0]?.id ?? null)
    } catch (loadError) {
      const accessFailure = getDashboardRequestAccessFailure(loadError)
      if (accessFailure === 'authentication') {
        setAuthRequired(true)
      } else if (accessFailure === 'permission') {
        setPermissionDenied(true)
      } else {
        setError(dashboardRequestErrorMessage(loadError, 'Failed to load document workflows'))
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  function resetManagedSubmissionKey() {
    managedSubmissionKeyRef.current = null
  }

  function managedUploads(): ManagedUpload[] {
    if (selectedTemplateId === 'contract_comparison') {
      return [
        ...(managedBaseFile ? [{ role: 'base_document', file: managedBaseFile }] : []),
        ...(managedComparisonFile
          ? [{ role: 'comparison_document', file: managedComparisonFile }]
          : []),
      ]
    }
    return managedFiles.map((file) => ({ role: 'documents', file }))
  }

  async function submitManagedJob() {
    setError(null)
    const parameters: Record<string, unknown> = {}
    if (instructions.trim()) {
      parameters.instructions = instructions.trim()
    }
    if (selectedTemplateId === 'document_redaction' && redactionPolicy.trim()) {
      parameters.redaction_policy = redactionPolicy.trim()
    }
    const uploads = managedUploads()
    const validationError = validateManagedDocumentSubmission(
      selectedTemplate,
      parameters,
      uploads,
    )
    if (validationError) {
      setError(validationError)
      return
    }

    setSubmittingManaged(true)
    try {
      const formData = new FormData()
      formData.append('template_id', selectedTemplateId)
      formData.append('parameters', JSON.stringify(parameters))
      uploads.forEach(({ role, file }) => formData.append(role, file))

      const idempotencyKey = managedSubmissionKeyRef.current ?? crypto.randomUUID()
      managedSubmissionKeyRef.current = idempotencyKey
      const response = await fetch('/api/dashboard/documents/jobs/submit', {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body: formData,
      })
      const payload = await response.json().catch(() => ({
        detail: 'Document service returned an invalid response',
      }))
      if (!response.ok) {
        throw new ApiRequestError(
          extractApiErrorMessage(payload, 'Failed to submit managed document job'),
          response.status,
        )
      }
      const job = payload as DocumentJob

      setManagedFiles([])
      setManagedBaseFile(null)
      setManagedComparisonFile(null)
      managedSubmissionKeyRef.current = null
      await loadData(job.id)
    } catch (submitError) {
      const message = describeDocumentRequestError(submitError)
      const accessFailure = getDashboardRequestAccessFailure(submitError)
      if (accessFailure === 'authentication') {
        setAuthRequired(true)
      } else if (accessFailure === 'permission') {
        setPermissionDenied(true)
      } else {
        try {
          const history = await readJson<DocumentJobHistory>(
            '/api/dashboard/documents/jobs?limit=20',
          )
          setJobs(history.items ?? [])
          setSelectedJobId(history.items?.[0]?.id ?? null)
        } catch {
          // Keep the original, actionable submission error.
        }
        setError(message)
      }
    } finally {
      setSubmittingManaged(false)
    }
  }

  async function cleanupFailedJob(job: DocumentJob) {
    setCleaningJobId(job.id)
    setError(null)
    try {
      await writeJson<DocumentJob>(
        `/api/dashboard/documents/jobs/${encodeURIComponent(job.id)}/cleanup`,
        { method: 'POST' },
      )
      await loadData(job.id)
    } catch (cleanupError) {
      const accessFailure = getDashboardRequestAccessFailure(cleanupError)
      if (accessFailure === 'authentication') setAuthRequired(true)
      else if (accessFailure === 'permission') setPermissionDenied(true)
      else setError(describeDocumentRequestError(cleanupError))
    } finally {
      setCleaningJobId(null)
    }
  }

  async function chooseDesktopFiles(target: 'documents' | 'base' | 'comparison') {
    if (!isDesktopRuntime()) {
      return
    }
    try {
      const result = (await window.mutxDesktop!.bridge.call('dialog.chooseFiles', {
        allow_multiple: target === 'documents',
      })) as BridgeResult<{ paths?: string[] }>
      if (!result.success) {
        throw new Error(result.error || 'No files selected')
      }
      const paths = result.paths ?? []
      if (target === 'documents') {
        setDesktopFiles(paths)
      } else if (target === 'base') {
        setDesktopBaseFile(paths[0] ?? null)
      } else {
        setDesktopComparisonFile(paths[0] ?? null)
      }
    } catch (bridgeError) {
      setError(bridgeError instanceof Error ? bridgeError.message : 'Failed to choose local files')
    }
  }

  async function submitDesktopLocalJob() {
    if (!isDesktopRuntime()) {
      return
    }

    setDesktopBusy(true)
    setError(null)
    try {
      const parameters: Record<string, unknown> = {}
      if (instructions.trim()) {
        parameters.instructions = instructions.trim()
      }
      if (redactionPolicy.trim()) {
        parameters.redaction_policy = redactionPolicy.trim()
      }

      const createResult = (await window.mutxDesktop!.bridge.call('documents.createJob', {
        template_id: selectedTemplateId,
        execution_mode: 'local',
        parameters,
      })) as BridgeResult<{ job?: DocumentJob }>
      if (!createResult.success || !createResult.job) {
        throw new Error(createResult.error || 'Failed to create local document job')
      }

      const jobId = createResult.job.id

      if (selectedTemplateId === 'contract_comparison') {
        if (!desktopBaseFile || !desktopComparisonFile) {
          throw new Error('Choose both a base document and a comparison document.')
        }
        for (const [role, filePath] of [
          ['base_document', desktopBaseFile],
          ['comparison_document', desktopComparisonFile],
        ] as const) {
          const registerResult = (await window.mutxDesktop!.bridge.call('documents.registerLocalArtifact', {
            job_id: jobId,
            role,
            kind: 'file',
            file_path: filePath,
          })) as BridgeResult<object>
          if (!registerResult.success) {
            throw new Error(registerResult.error || `Failed to register ${role}`)
          }
        }
      } else {
        if (desktopFiles.length === 0) {
          throw new Error('Choose at least one local document.')
        }
        for (const filePath of desktopFiles) {
          const registerResult = (await window.mutxDesktop!.bridge.call('documents.registerLocalArtifact', {
            job_id: jobId,
            role: 'documents',
            kind: 'file',
            file_path: filePath,
          })) as BridgeResult<object>
          if (!registerResult.success) {
            throw new Error(registerResult.error || 'Failed to register local artifact')
          }
        }
      }

      const runResult = (await window.mutxDesktop!.bridge.call('documents.runLocal', {
        job_id: jobId,
      })) as BridgeResult<{ job?: DocumentJob }>
      if (!runResult.success || !runResult.job) {
        throw new Error(runResult.error || 'Failed to run local document workflow')
      }

      setDesktopFiles([])
      setDesktopBaseFile(null)
      setDesktopComparisonFile(null)
      await loadData(jobId)
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Failed to run local document workflow')
    } finally {
      setDesktopBusy(false)
    }
  }

  const jobStats = useMemo(() => {
    const running = jobs.filter((item) => item.status === 'running').length
    const queued = jobs.filter((item) => item.status === 'queued' || item.status === 'created').length
    const completed = jobs.filter((item) => item.status === 'completed').length
    const failed = jobs.filter((item) => item.status === 'failed').length
    return { running, queued, completed, failed }
  }, [jobs])

  if (loading) return <LiveLoading title="Documents" />
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to queue and inspect document workflow jobs."
      />
    )
  }
  if (permissionDenied) {
    return <LiveForbidden title="Document permission required" message="Your account cannot queue or inspect document workflows. Submission and cleanup controls are unavailable." />
  }
  if (error && templates.length === 0 && jobs.length === 0) {
    return <LiveErrorState title="Document workflows unavailable" message={error} />
  }

  return (
    <div className="space-y-4">
      {error ? <LiveErrorState title="Workflow issue" message={error} /> : null}

      <LiveKpiGrid>
        <LiveStatCard label="Templates" value={String(templates.length)} detail="Document workflow templates wired into MUTX." />
        <LiveStatCard label="Queued" value={String(jobStats.queued)} detail="Jobs waiting for dispatch or pickup." status={asDashboardStatus(jobStats.queued > 0 ? 'warning' : 'idle')} />
        <LiveStatCard label="Running" value={String(jobStats.running)} detail="Active managed or local document executions." status={asDashboardStatus(jobStats.running > 0 ? 'running' : 'idle')} />
        <LiveStatCard label="Completed" value={String(jobStats.completed)} detail="Successful workflows with artifacts available for inspection." status="success" />
        <LiveStatCard label="Failed" value={String(jobStats.failed)} detail="Workflows that need operator follow-up." status={asDashboardStatus(jobStats.failed > 0 ? 'failed' : 'healthy')} />
      </LiveKpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)]">
        <LivePanel
          title="Launch workflow"
          meta={selectedTemplate?.name || 'Select template'}
          action={
            <FeatureHint
              detail="Managed submissions validate required inputs before creating canonical history. Repeated submissions reuse an idempotency key until the form changes."
            />
          }
        >
          <div className="space-y-4">
            <label className="block space-y-2">
              <span className="text-xs uppercase tracking-[0.18em] text-slate-500">Template</span>
              <select
                value={selectedTemplateId}
                onChange={(event) => {
                  setSelectedTemplateId(event.target.value)
                  resetManagedSubmissionKey()
                }}
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white"
              >
                {templates.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>

            {selectedTemplate ? (
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <p className="text-sm text-white">{selectedTemplate.summary}</p>
                <p className="mt-2 text-sm text-slate-400">{selectedTemplate.description}</p>
              </div>
            ) : null}

            <label className="block space-y-2">
              <span className="text-xs uppercase tracking-[0.18em] text-slate-500">Instructions</span>
              <textarea
                value={instructions}
                onChange={(event) => {
                  setInstructions(event.target.value)
                  resetManagedSubmissionKey()
                }}
                className="min-h-24 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white"
                placeholder="Optional analyst instructions for the workflow"
              />
            </label>

            {selectedTemplateId === 'document_redaction' ? (
              <label className="block space-y-2">
                <span className="text-xs uppercase tracking-[0.18em] text-slate-500">Redaction Policy</span>
                <textarea
                  value={redactionPolicy}
                  onChange={(event) => {
                    setRedactionPolicy(event.target.value)
                    resetManagedSubmissionKey()
                  }}
                  className="min-h-24 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white"
                  placeholder="Describe what must be redacted"
                />
              </label>
            ) : null}

            {selectedTemplateId === 'contract_comparison' ? (
              <div className="grid gap-4 md:grid-cols-2">
                <label className="block space-y-2">
                  <span className="text-xs uppercase tracking-[0.18em] text-slate-500">Base Document</span>
                  <input
                    type="file"
                    onChange={(event) => {
                      setManagedBaseFile(event.target.files?.[0] ?? null)
                      resetManagedSubmissionKey()
                    }}
                    className="block w-full text-sm text-slate-300"
                  />
                </label>
                <label className="block space-y-2">
                  <span className="text-xs uppercase tracking-[0.18em] text-slate-500">Comparison Document</span>
                  <input
                    type="file"
                    onChange={(event) => {
                      setManagedComparisonFile(event.target.files?.[0] ?? null)
                      resetManagedSubmissionKey()
                    }}
                    className="block w-full text-sm text-slate-300"
                  />
                </label>
              </div>
            ) : (
              <label className="block space-y-2">
                <span className="text-xs uppercase tracking-[0.18em] text-slate-500">Managed upload</span>
                <input
                  type="file"
                  multiple
                  onChange={(event) => {
                    setManagedFiles(Array.from(event.target.files ?? []))
                    resetManagedSubmissionKey()
                  }}
                  className="block w-full text-sm text-slate-300"
                />
              </label>
            )}

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void submitManagedJob()}
                disabled={submittingManaged}
                className="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-100 transition hover:border-cyan-300/50 disabled:opacity-50"
              >
                {submittingManaged ? 'Submitting managed job…' : 'Submit managed job'}
              </button>

              {isDesktopRuntime() ? (
                <button
                  type="button"
                  onClick={() => void submitDesktopLocalJob()}
                  disabled={desktopBusy}
                  className="rounded-full border border-amber-300/25 bg-amber-300/10 px-4 py-2 text-sm text-amber-100 transition hover:border-amber-200/45 disabled:opacity-50"
                >
                  {desktopBusy ? 'Running local job…' : 'Run locally on this desktop'}
                </button>
              ) : null}
            </div>

            {isDesktopRuntime() ? (
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">Desktop local lane</p>
                    <p className="mt-1 text-sm text-slate-400">
                      Use the native bridge to choose local files, execute with the local engine, and upload result artifacts back into MUTX.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {selectedTemplateId === 'contract_comparison' ? (
                      <>
                        <button
                          type="button"
                          onClick={() => void chooseDesktopFiles('base')}
                          className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-slate-200"
                        >
                          Choose base document
                        </button>
                        <button
                          type="button"
                          onClick={() => void chooseDesktopFiles('comparison')}
                          className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-slate-200"
                        >
                          Choose comparison document
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        onClick={() => void chooseDesktopFiles('documents')}
                        className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-slate-200"
                      >
                        Choose local files
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-3 text-xs text-slate-500">
                  {selectedTemplateId === 'contract_comparison'
                    ? `Base: ${desktopBaseFile || 'not selected'} · Comparison: ${desktopComparisonFile || 'not selected'}`
                    : desktopFiles.length > 0
                      ? desktopFiles.join(' • ')
                      : 'No local files selected yet.'}
                </div>
              </div>
            ) : null}
          </div>
        </LivePanel>

        <LivePanel title="Recent jobs" meta={`${jobs.length} jobs`}>
          {jobs.length === 0 ? (
            <LiveEmptyState
              title="No document jobs yet"
              message="Queue a managed workflow or run one locally from the desktop bridge."
            />
          ) : (
            <div className="space-y-3">
              {jobs.map((job) => {
                const active = selectedJobId === job.id
                return (
                  <button
                    key={job.id}
                    type="button"
                    onClick={() => setSelectedJobId(job.id)}
                    className={`w-full rounded-xl border p-4 text-left transition ${
                      active
                        ? 'border-cyan-400/35 bg-cyan-400/10'
                        : 'border-white/10 bg-white/[0.02] hover:border-white/20'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-mono text-sm text-white">{job.id}</p>
                        <p className="mt-1 text-sm text-slate-400">
                          {job.template_id} · {job.execution_mode}
                        </p>
                        <div className="mt-2 text-xs text-slate-500">
                          created {job.created_at ? formatRelativeTime(job.created_at) : 'n/a'}
                        </div>
                      </div>
                      <StatusBadge status={asDashboardStatus(job.status)} label={job.status} />
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </LivePanel>
      </div>

      <LivePanel title="Job detail" meta={selectedJob ? selectedJob.run_id : 'select a job'}>
        {selectedJob ? (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="space-y-4">
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-mono text-sm text-white">{selectedJob.id}</p>
                    <p className="mt-1 text-sm text-slate-400">
                      {selectedJob.template_id} · {selectedJob.execution_mode}
                    </p>
                  </div>
                  <StatusBadge status={asDashboardStatus(selectedJob.status)} label={selectedJob.status} />
                </div>
                {selectedJob.error_message ? (
                  <p className="mt-3 text-sm text-rose-300">{selectedJob.error_message}</p>
                ) : null}
                <div className="mt-4 flex flex-wrap gap-4 text-xs text-slate-500">
                  <span>Run {selectedJob.run_id}</span>
                  <span>{selectedJob.artifacts.length} artifacts</span>
                  {selectedJob.completed_at ? (
                    <span>finished {formatRelativeTime(selectedJob.completed_at)}</span>
                  ) : null}
                </div>
                <div className="mt-4 flex flex-wrap gap-3">
                  <Link href="/dashboard/runs" className="text-sm text-cyan-300 underline-offset-4 hover:underline">
                    Open runs surface
                  </Link>
                  <Link href="/dashboard/traces" className="text-sm text-cyan-300 underline-offset-4 hover:underline">
                    Open traces surface
                  </Link>
                </div>
                {['created', 'uploading', 'failed'].includes(selectedJob.status) ? (
                  <div className="mt-4 rounded-lg border border-amber-300/20 bg-amber-300/[0.06] p-3">
                    <p className="text-sm text-amber-100">
                      {selectedJob.status === 'failed'
                        ? 'If the original files are still selected, submit again to retry safely; otherwise clean up this failed submission.'
                        : 'This submission has not been dispatched. You can remove its staged artifacts safely.'}
                    </p>
                    <button
                      type="button"
                      onClick={() => void cleanupFailedJob(selectedJob)}
                      disabled={cleaningJobId === selectedJob.id}
                      className="mt-3 rounded-full border border-amber-300/25 px-3 py-1.5 text-xs text-amber-100 disabled:opacity-50"
                    >
                      {cleaningJobId === selectedJob.id
                        ? 'Cleaning up…'
                        : 'Cancel and clean up'}
                    </button>
                  </div>
                ) : null}
              </div>

              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Artifacts</p>
                <div className="mt-3 space-y-3">
                  {selectedJob.artifacts.length > 0 ? (
                    selectedJob.artifacts.map((artifact) => (
                      <div key={artifact.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 px-3 py-2">
                        <div>
                          <p className="text-sm text-white">{artifact.filename}</p>
                          <p className="mt-1 text-xs text-slate-500">
                            {artifact.role} · {artifact.kind} · {artifact.storage_backend}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <a
                            href={`/api/dashboard/documents/jobs/${encodeURIComponent(selectedJob.id)}/artifacts/${encodeURIComponent(artifact.id)}`}
                            className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-slate-200"
                          >
                            Download
                          </a>
                          {isDesktopRuntime() ? (
                            <button
                              type="button"
                              onClick={async () => {
                                try {
                                  const result = (await window.mutxDesktop!.bridge.call('documents.downloadArtifact', {
                                    job_id: selectedJob.id,
                                    artifact_id: artifact.id,
                                  })) as BridgeResult<{ path?: string }>
                                  if (!result.success || !result.path) {
                                    throw new Error(result.error || 'Failed to download artifact')
                                  }
                                  await window.mutxDesktop!.bridge.system.revealInFinder(result.path)
                                } catch (downloadError) {
                                  setError(downloadError instanceof Error ? downloadError.message : 'Failed to open artifact')
                                }
                              }}
                              className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-slate-200"
                            >
                              Reveal in Finder
                            </button>
                          ) : null}
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-slate-500">No artifacts have been registered for this job yet.</p>
                  )}
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Parameters</p>
                <pre className="mt-3 overflow-x-auto text-xs text-slate-300">
                  {JSON.stringify(selectedJob.parameters || {}, null, 2)}
                </pre>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Result summary</p>
                <pre className="mt-3 overflow-x-auto text-xs text-slate-300">
                  {JSON.stringify(selectedJob.result_summary || {}, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        ) : (
          <LiveEmptyState
            title="Select a document job"
            message="Choose a job from the recent list to inspect artifacts and linked run metadata."
          />
        )}
      </LivePanel>
    </div>
  )
}
