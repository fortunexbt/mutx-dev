"use client";

import { useEffect, useMemo, useState } from "react";

import { ApiRequestError, readJson, writeJson } from "@/components/app/http";
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from "@/components/dashboard/dashboardRequestAccess";
import {
  LiveAuthRequired,
  LiveEmptyState,
  LiveErrorState,
  LiveForbidden,
  LiveKpiGrid,
  LiveLoading,
  LivePanel,
  LiveStatCard,
  asDashboardStatus,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { FeatureHint } from "@/components/dashboard/FeatureHint";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

type ReasoningTemplate = {
  id: string;
  name: string;
  summary: string;
  description: string;
  supports_managed: boolean;
  supports_local: boolean;
};

type ReasoningArtifact = {
  id: string;
  role: string;
  kind: string;
  storage_backend: string;
  filename: string;
};

type ReasoningJob = {
  id: string;
  run_id: string;
  template_id: string;
  execution_mode: string;
  status: string;
  parameters: Record<string, unknown>;
  result_summary: Record<string, unknown>;
  error_message?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  artifacts: ReasoningArtifact[];
};

type ReasoningJobHistory = {
  items: ReasoningJob[];
  total: number;
};

async function uploadContextArtifact(jobId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("role", "context");
  formData.append("kind", "file");

  const response = await fetch(`/api/dashboard/reasoning/jobs/${encodeURIComponent(jobId)}/artifacts`, {
    method: "POST",
    body: formData,
  });
  const payload = await response.json().catch(() => ({ detail: "Failed to upload reasoning context" }));
  if (!response.ok) {
    throw new ApiRequestError(
      typeof payload?.detail === "string" ? payload.detail : "Failed to upload reasoning context",
      response.status,
    );
  }
  return payload as ReasoningArtifact;
}

export function ReasoningPageClient() {
  const [loading, setLoading] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [templates, setTemplates] = useState<ReasoningTemplate[]>([]);
  const [jobs, setJobs] = useState<ReasoningJob[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("autoreason_refine");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [taskPrompt, setTaskPrompt] = useState("");
  const [incumbent, setIncumbent] = useState("");
  const [rubric, setRubric] = useState("");
  const [contextFiles, setContextFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const selectedTemplate = useMemo(
    () => templates.find((item) => item.id === selectedTemplateId) ?? null,
    [templates, selectedTemplateId],
  );
  const selectedJob = useMemo(
    () => jobs.find((item) => item.id === selectedJobId) ?? null,
    [jobs, selectedJobId],
  );

  async function loadData(nextJobId?: string) {
    setLoading(true);
    setError(null);
    setAuthRequired(false);
    setPermissionDenied(false);

    try {
      const [templateResponse, jobsResponse] = await Promise.all([
        readJson<ReasoningTemplate[]>("/api/dashboard/reasoning/templates"),
        readJson<ReasoningJobHistory>("/api/dashboard/reasoning/jobs?limit=20"),
      ]);
      setTemplates(templateResponse);
      setJobs(jobsResponse.items ?? []);
      setSelectedTemplateId((current) => current || templateResponse[0]?.id || "autoreason_refine");
      setSelectedJobId(nextJobId ?? jobsResponse.items?.[0]?.id ?? null);
    } catch (loadError) {
      const accessFailure = getDashboardRequestAccessFailure(loadError);
      if (accessFailure === "authentication") {
        setAuthRequired(true);
      } else if (accessFailure === "permission") {
        setPermissionDenied(true);
      } else {
        setError(dashboardRequestErrorMessage(loadError, "Failed to load reasoning workflows"));
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  async function submitManagedJob() {
    if (!taskPrompt.trim()) {
      setError("Task prompt is required.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const parameters: Record<string, unknown> = {
        task_prompt: taskPrompt.trim(),
      };
      if (incumbent.trim()) {
        parameters.incumbent = incumbent.trim();
      }
      if (rubric.trim()) {
        parameters.rubric = rubric.trim();
      }

      const job = await writeJson<ReasoningJob>("/api/dashboard/reasoning/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template_id: selectedTemplateId,
          execution_mode: "managed",
          parameters,
        }),
      });

      for (const file of contextFiles) {
        await uploadContextArtifact(job.id, file);
      }

      await writeJson<ReasoningJob>(`/api/dashboard/reasoning/jobs/${encodeURIComponent(job.id)}/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "managed" }),
      });

      setTaskPrompt("");
      setIncumbent("");
      setRubric("");
      setContextFiles([]);
      await loadData(job.id);
    } catch (submitError) {
      const accessFailure = getDashboardRequestAccessFailure(submitError);
      if (accessFailure === "authentication") setAuthRequired(true);
      else if (accessFailure === "permission") setPermissionDenied(true);
      else setError(dashboardRequestErrorMessage(submitError, "Failed to queue reasoning job"));
    } finally {
      setSubmitting(false);
    }
  }

  const jobStats = useMemo(() => {
    const queued = jobs.filter((job) => job.status === "queued" || job.status === "created").length;
    const running = jobs.filter((job) => job.status === "running").length;
    const completed = jobs.filter((job) => job.status === "completed").length;
    const failed = jobs.filter((job) => job.status === "failed").length;
    return { queued, running, completed, failed };
  }, [jobs]);

  if (loading) return <LiveLoading title="Reasoning" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to launch and inspect Autoreason refinement jobs."
      />
    );
  }
  if (permissionDenied) {
    return <LiveForbidden title="Reasoning permission required" message="Your account cannot launch or inspect reasoning workflows. Submission controls are unavailable." />;
  }
  if (error && templates.length === 0 && jobs.length === 0) {
    return <LiveErrorState title="Reasoning workflows unavailable" message={error} />;
  }

  return (
    <div className="space-y-4">
      <LiveKpiGrid>
        <LiveStatCard
          label="Templates"
          value={String(templates.length)}
          detail="Reasoning workflow templates available in MUTX."
        />
        <LiveStatCard
          label="Queued"
          value={String(jobStats.queued)}
          detail="Jobs waiting for a reasoning worker to pick them up."
          status={asDashboardStatus(jobStats.queued > 0 ? "warning" : "idle")}
        />
        <LiveStatCard
          label="Running"
          value={String(jobStats.running)}
          detail="Autoreason loops actively judging or refining."
          status={asDashboardStatus(jobStats.running > 0 ? "running" : "idle")}
        />
        <LiveStatCard
          label="Completed"
          value={String(jobStats.completed)}
          detail="Jobs that finished with a final incumbent and artifacts."
          status="success"
        />
        <LiveStatCard
          label="Failed"
          value={String(jobStats.failed)}
          detail="Reasoning jobs that need operator follow-up."
          status={asDashboardStatus(jobStats.failed > 0 ? "failed" : "healthy")}
        />
      </LiveKpiGrid>

      {error ? <LiveErrorState title="Reasoning update failed" message={error} /> : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(380px,0.95fr)]">
        <LivePanel
          title="Launch autoreason"
          meta={selectedTemplate?.name || "Select template"}
          action={
            <FeatureHint
              detail="Autoreason launch creates a persisted refinement job. Judging results, artifacts, and linked runs remain visible for operator review."
            />
          }
        >
          <div className="space-y-4">
            <label className="block space-y-2">
              <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                Template
              </span>
              <select
                value={selectedTemplateId}
                onChange={(event) => setSelectedTemplateId(event.target.value)}
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white"
              >
                {templates.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.name}
                  </option>
                ))}
              </select>
            </label>

            {selectedTemplate ? (
              <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4 text-sm text-slate-300">
                <p className="font-medium text-white">{selectedTemplate.summary}</p>
                <p className="mt-2 text-slate-400">{selectedTemplate.description}</p>
              </div>
            ) : null}

            <label className="block space-y-2">
              <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                Task prompt
              </span>
              <textarea
                value={taskPrompt}
                onChange={(event) => setTaskPrompt(event.target.value)}
                className="min-h-32 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white"
                placeholder="What should Autoreason improve, decide, or rewrite?"
              />
            </label>

            <label className="block space-y-2">
              <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                Incumbent answer
              </span>
              <textarea
                value={incumbent}
                onChange={(event) => setIncumbent(event.target.value)}
                className="min-h-28 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white"
                placeholder="Optional starting answer. Leave empty to draft from scratch."
              />
            </label>

            <label className="block space-y-2">
              <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                Rubric
              </span>
              <textarea
                value={rubric}
                onChange={(event) => setRubric(event.target.value)}
                className="min-h-24 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white"
                placeholder="Optional evaluation rubric for the judge panel."
              />
            </label>

            <label className="block space-y-2">
              <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                Context files
              </span>
              <input
                type="file"
                multiple
                accept=".txt,.md,.pdf,.json,.yaml,.yml,.xml,.csv,.py,.js,.ts,.tsx,.html,.css,.log,.sh,.bash"
                onChange={(event) => setContextFiles(Array.from(event.target.files ?? []))}
                className="block w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-300"
              />
              {contextFiles.length > 0 ? (
                <ul className="space-y-1 text-xs text-slate-400">
                  {contextFiles.map((file) => (
                    <li key={`${file.name}-${file.size}`}>{file.name}</li>
                  ))}
                </ul>
              ) : null}
            </label>

            <button
              type="button"
              onClick={() => void submitManagedJob()}
              disabled={submitting}
              className="inline-flex items-center justify-center rounded-full border border-sky-400/30 bg-sky-500/12 px-5 py-2.5 text-sm font-medium text-slate-50 transition hover:bg-sky-500/18 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "Queueing..." : "Queue managed job"}
            </button>
          </div>
        </LivePanel>

        <div className="space-y-4">
          <LivePanel title="Reasoning history" meta={`${jobs.length} jobs`}>
            {jobs.length === 0 ? (
              <LiveEmptyState
                title="No reasoning jobs yet"
                message="Your first Autoreason run will show up here with artifacts and run linkage."
              />
            ) : (
              <div className="space-y-3">
                {jobs.map((job) => {
                  const isSelected = selectedJobId === job.id;
                  const winner = typeof job.result_summary?.winner === "string" ? job.result_summary.winner : null;
                  const passCount = typeof job.result_summary?.pass_count === "number" ? job.result_summary.pass_count : null;
                  return (
                    <button
                      key={job.id}
                      type="button"
                      onClick={() => setSelectedJobId(job.id)}
                      className={`w-full rounded-2xl border p-4 text-left transition ${
                        isSelected ? "border-sky-400/40 bg-sky-500/10" : "border-white/10 bg-white/[0.02]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-white">{job.id}</p>
                          <p className="mt-1 text-xs text-slate-400">
                            {job.template_id} · {job.execution_mode}
                          </p>
                        </div>
                        <StatusBadge status={asDashboardStatus(job.status)} label={job.status} />
                      </div>
                      <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
                        <span>created {formatRelativeTime(job.created_at)}</span>
                        {job.completed_at ? <span>finished {formatRelativeTime(job.completed_at)}</span> : null}
                        {winner ? <span>winner {winner}</span> : null}
                        {passCount !== null ? <span>{passCount} passes</span> : null}
                      </div>
                      {job.error_message ? (
                        <p className="mt-3 text-sm text-rose-300">{job.error_message}</p>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            )}
          </LivePanel>

          <LivePanel title="Selected job" meta={selectedJob?.id || "None selected"}>
            {selectedJob ? (
              <div className="space-y-4 text-sm text-slate-300">
                <div className="flex flex-wrap items-center gap-3">
                  <StatusBadge status={asDashboardStatus(selectedJob.status)} label={selectedJob.status} />
                  <span className="text-slate-500">run {selectedJob.run_id}</span>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Winner</p>
                    <p className="mt-2 text-lg font-medium text-white">
                      {typeof selectedJob.result_summary?.winner === "string"
                        ? selectedJob.result_summary.winner
                        : "Pending"}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Passes</p>
                    <p className="mt-2 text-lg font-medium text-white">
                      {typeof selectedJob.result_summary?.pass_count === "number"
                        ? selectedJob.result_summary.pass_count
                        : "-"}
                    </p>
                  </div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Input task</p>
                  <p className="mt-2 whitespace-pre-wrap text-slate-300">
                    {typeof selectedJob.parameters?.task_prompt === "string"
                      ? selectedJob.parameters.task_prompt
                      : "No task prompt recorded."}
                  </p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Artifacts</p>
                  {selectedJob.artifacts.length === 0 ? (
                    <p className="mt-2 text-slate-500">No artifacts synced yet.</p>
                  ) : (
                    <div className="mt-3 space-y-2">
                      {selectedJob.artifacts.map((artifact) => (
                        <a
                          key={artifact.id}
                          href={`/api/dashboard/reasoning/jobs/${encodeURIComponent(selectedJob.id)}/artifacts/${encodeURIComponent(artifact.id)}`}
                          className="flex items-center justify-between rounded-xl border border-white/10 bg-black/10 px-3 py-2 text-sm text-slate-200 transition hover:border-sky-400/40 hover:text-white"
                        >
                          <span>{artifact.filename}</span>
                          <span className="text-xs text-slate-500">
                            {artifact.role} · {artifact.kind}
                          </span>
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <LiveEmptyState
                title="No reasoning job selected"
                message="Pick a job from the history panel to inspect winner state and artifacts."
              />
            )}
          </LivePanel>
        </div>
      </div>
    </div>
  );
}
