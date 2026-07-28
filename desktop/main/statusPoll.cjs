const path = require("path");

const GOVERNANCE_STATES = new Set([
  "running",
  "stopped",
  "degraded",
  "not_installed",
  "error",
]);

const SOURCE_LABELS = {
  context: "Runtime context",
  auth: "Authentication status",
  runtime: "Runtime inspection",
  governance: "Governance status",
  sessions: "Assistant sessions",
  controlPlane: "Local control plane status",
};

function asRecord(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function pickString(value, keys) {
  const record = asRecord(value);
  if (!record) {
    return null;
  }

  for (const key of keys) {
    const candidate = record[key];
    if (typeof candidate === "string" && candidate.trim().length > 0) {
      return candidate;
    }
  }
  return null;
}

function resolveCurrentBinding(runtimeInfo) {
  const openclaw = asRecord(runtimeInfo?.openclaw);
  const currentBinding = asRecord(openclaw?.current_binding);
  if (currentBinding) {
    return currentBinding;
  }

  const bindings = Array.isArray(openclaw?.bindings) ? openclaw.bindings : [];
  for (const binding of bindings) {
    const record = asRecord(binding);
    if (record) {
      return record;
    }
  }
  return null;
}

function publicSourceError(sourceName, error) {
  const label = SOURCE_LABELS[sourceName] || "Desktop status source";
  const message = error instanceof Error ? error.message.toLowerCase() : "";

  if (message.includes("timeout") || message.includes("timed out")) {
    return `${label} timed out. Retry from Desktop Settings.`;
  }
  if (message.includes("bridge not ready") || message.includes("bridge not running")) {
    return `${label} is unavailable while the desktop bridge recovers.`;
  }
  return `${label} is unavailable. Retry from Desktop Settings.`;
}

function normalizeSettledResult(sourceName, result) {
  if (result.status === "fulfilled") {
    return {
      ok: true,
      value: result.value,
      error: null,
    };
  }

  return {
    ok: false,
    value: null,
    error: publicSourceError(sourceName, result.reason),
  };
}

async function collectStatusSources(requests, observedAt = new Date().toISOString()) {
  const entries = Object.entries(requests);
  const settled = await Promise.allSettled(
    entries.map(([, request]) => Promise.resolve().then(request)),
  );
  const results = {};

  entries.forEach(([sourceName], index) => {
    results[sourceName] = normalizeSettledResult(sourceName, settled[index]);
  });

  return { observedAt, results };
}

function getSourceValue(results, sourceName) {
  const result = results[sourceName];
  return result?.ok ? result.value : null;
}

function buildSourceUpdates(results, observedAt) {
  return Object.fromEntries(
    Object.entries(results).map(([sourceName, result]) => [
      sourceName,
      {
        available: result.ok,
        observedAt,
        lastError: result.error,
      },
    ]),
  );
}

function mapGovernanceState(governanceInfo) {
  const reportedStatus = pickString(governanceInfo, ["status"]);
  const health = GOVERNANCE_STATES.has(reportedStatus) ? reportedStatus : "error";

  return {
    available: health === "running",
    health,
    socketPath: null,
  };
}

function summarizeControlPlaneState(context, sourceResult, localControlPlane) {
  if (!sourceResult?.ok) {
    return {
      ready: false,
      state: "error",
      exists: null,
      lastError: sourceResult?.error || "Local control plane status is unavailable.",
    };
  }

  if (localControlPlane?.ready) {
    return {
      ready: true,
      state: "ready",
      exists: true,
      lastError: null,
    };
  }

  return {
    ready: false,
    state: context.mode === "local" ? "degraded" : "stopped",
    exists:
      typeof localControlPlane?.exists === "boolean"
        ? localControlPlane.exists
        : Boolean(localControlPlane?.path),
    lastError:
      context.mode === "local"
        ? "Local control plane is not ready. Open Desktop Settings to start or repair it."
        : null,
  };
}

function summarizeRuntimeState({
  context,
  bridgeState,
  serverState,
  results,
  localControlPlane,
  assistantFound,
}) {
  if (!serverState.ready) {
    return {
      state:
        serverState.state === "starting" || serverState.state === "restarting"
          ? serverState.state
          : "error",
      lastError:
        serverState.lastError ||
        "Desktop UI is unavailable. Restart MUTX; if it persists, reinstall the application.",
    };
  }

  if (!bridgeState.ready) {
    return {
      state:
        bridgeState.state === "starting" || bridgeState.state === "restarting"
          ? bridgeState.state
          : "degraded",
      lastError:
        bridgeState.lastError ||
        "Desktop bridge is unavailable. Retry from Desktop Settings while it recovers.",
    };
  }

  if (!results.runtime?.ok) {
    return { state: "error", lastError: results.runtime.error };
  }

  if (context.mode === "local" && !results.controlPlane?.ok) {
    return { state: "degraded", lastError: results.controlPlane.error };
  }

  if (context.mode === "local" && !localControlPlane?.ready) {
    return {
      state: "degraded",
      lastError: "Local control plane is not ready. Open Desktop Settings to start or repair it.",
    };
  }

  if (!assistantFound) {
    return {
      state: "degraded",
      lastError: "No assistant is bound. Open Desktop Settings to finish runtime setup.",
    };
  }

  if (!results.sessions?.ok) {
    return { state: "degraded", lastError: results.sessions.error };
  }

  return { state: "ready", lastError: null };
}

function buildDesktopStatusSnapshot({
  observedAt,
  results,
  serverState,
  bridgeState,
  appVersion,
}) {
  const context = asRecord(getSourceValue(results, "context")) || {
    mode: "unknown",
    apiUrl: "",
  };
  const authInfo = asRecord(getSourceValue(results, "auth"));
  const runtimeInfo = asRecord(getSourceValue(results, "runtime"));
  const governanceInfo = asRecord(getSourceValue(results, "governance"));
  const sessionInfo = getSourceValue(results, "sessions");
  const controlPlaneInfo = asRecord(getSourceValue(results, "controlPlane"));
  const openclawInfo = asRecord(runtimeInfo?.openclaw);
  const gatewayInfo = asRecord(openclawInfo?.gateway);
  const currentBinding = resolveCurrentBinding(runtimeInfo);
  const currentAssistantId = pickString(currentBinding, ["assistant_id", "agent_id", "id"]);
  const currentAssistantName = pickString(currentBinding, ["assistant_name", "name"]);
  const currentAssistantWorkspace = pickString(currentBinding, ["workspace"]);
  const openclawBinaryPath = pickString(openclawInfo, ["binary_path"]);
  const apiUrl = pickString(context, ["apiUrl"]) || pickString(authInfo, ["api_url"]);
  const contextMode = context.mode === "local" || context.mode === "hosted" ? context.mode : null;
  const mode =
    contextMode ||
    (results.context?.ok && results.controlPlane?.ok
      ? controlPlaneInfo?.ready
        ? "local"
        : "hosted"
      : "unknown");
  const faramesh = results.governance?.ok
    ? mapGovernanceState(governanceInfo)
    : { available: false, health: "error", socketPath: null };
  const controlPlaneState = summarizeControlPlaneState(
    { mode },
    results.controlPlane,
    controlPlaneInfo,
  );

  let assistant;
  if (!results.runtime?.ok) {
    assistant = {
      found: false,
      name: null,
      agentId: null,
      workspace: null,
      gatewayStatus: null,
      sessionCount: null,
      state: "error",
      lastError: results.runtime.error,
    };
  } else if (currentBinding) {
    assistant = {
      found: true,
      name: currentAssistantName,
      agentId: currentAssistantId,
      workspace: currentAssistantWorkspace,
      gatewayStatus: pickString(gatewayInfo, ["status"]),
      sessionCount: Array.isArray(sessionInfo) ? sessionInfo.length : null,
      state: results.sessions?.ok ? "ready" : "degraded",
      lastError: results.sessions?.ok ? null : results.sessions?.error,
    };
  } else {
    assistant = {
      found: false,
      name: null,
      agentId: null,
      workspace: null,
      gatewayStatus: null,
      sessionCount: results.sessions?.ok ? 0 : null,
      state: !results.auth?.ok
        ? "error"
        : authInfo?.authenticated
          ? "degraded"
          : "starting",
      lastError: !results.auth?.ok
        ? results.auth.error
        : authInfo?.authenticated
          ? "No assistant is bound. Open Desktop Settings to finish runtime setup."
          : null,
    };
  }

  const runtime = summarizeRuntimeState({
    context: { mode },
    bridgeState,
    serverState,
    results,
    localControlPlane: controlPlaneInfo,
    assistantFound: Boolean(currentBinding),
  });

  return {
    mode,
    apiUrl,
    apiHealth: apiUrl ? (apiUrl.includes("localhost") || apiUrl.includes("127.0.0.1") ? "local" : "cloud") : "unknown",
    authenticated: results.auth?.ok ? Boolean(authInfo?.authenticated) : false,
    user: results.auth?.ok ? authInfo?.user || null : null,
    openclaw: results.runtime?.ok
      ? {
          binaryPath: openclawBinaryPath ? path.basename(openclawBinaryPath) : null,
          health: pickString(gatewayInfo, ["status"]) || "unknown",
          gatewayUrl: pickString(gatewayInfo, ["gateway_url"]),
        }
      : {
          binaryPath: null,
          health: "unavailable",
          gatewayUrl: null,
        },
    faramesh,
    uiServer: { ...serverState },
    localControlPlane: {
      ready: controlPlaneState.ready,
      path: results.controlPlane?.ok ? controlPlaneInfo?.path || null : null,
      state: controlPlaneState.state,
      exists: controlPlaneState.exists,
      lastError: controlPlaneState.lastError,
    },
    runtime,
    assistant,
    bridge: { ...bridgeState },
    cliAvailable: results.runtime?.ok ? Boolean(openclawBinaryPath) : false,
    mutxVersion: appVersion,
    sourceUpdates: buildSourceUpdates(results, observedAt),
  };
}

module.exports = {
  buildDesktopStatusSnapshot,
  collectStatusSources,
  mapGovernanceState,
  publicSourceError,
};
