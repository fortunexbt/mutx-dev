{{/* Expand the chart name. */}}
{{- define "mutx.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Create a default fully qualified app name. */}}
{{- define "mutx.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/* Common chart labels. */}}
{{- define "mutx.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "mutx.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* Labels shared by every component in a release. */}}
{{- define "mutx.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mutx.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* Immutable selector labels for one workload component. */}}
{{- define "mutx.componentSelectorLabels" -}}
{{ include "mutx.selectorLabels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/* Resolve the ServiceAccount used by normal chart workloads. */}}
{{- define "mutx.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "mutx.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/* Resolve the data claim; an empty result means an ephemeral emptyDir. */}}
{{- define "mutx.persistenceClaimName" -}}
{{- if .Values.persistence.enabled }}
{{- default (printf "%s-data" (include "mutx.fullname" .)) .Values.persistence.existingClaim }}
{{- end }}
{{- end }}

{{/* Resolve API/frontend secret names. */}}
{{- define "mutx.apiSecretName" -}}
{{- if .Values.api.existingSecret }}
{{- .Values.api.existingSecret }}
{{- else if .Values.api.secretEnv }}
{{- printf "%s-api-env" (include "mutx.fullname" .) }}
{{- end }}
{{- end }}

{{- define "mutx.frontendSecretName" -}}
{{- if .Values.frontend.existingSecret }}
{{- .Values.frontend.existingSecret }}
{{- else if .Values.frontend.secretEnv }}
{{- printf "%s-frontend-env" (include "mutx.fullname" .) }}
{{- end }}
{{- end }}

{{/* Image pull secrets shared by pods. */}}
{{- define "mutx.imagePullSecrets" -}}
{{- with .Values.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}

{{/* Fail early for combinations that render but cannot safely operate. */}}
{{- define "mutx.validateValues" -}}
{{- $environment := lower (toString (default "development" (get .Values.api.env "ENVIRONMENT"))) }}
{{- $isProduction := or (eq $environment "production") (eq $environment "prod") }}
{{- if and .Values.api.existingSecret .Values.api.secretEnv }}
{{- fail "api.existingSecret and api.secretEnv are mutually exclusive" }}
{{- end }}
{{- if and .Values.frontend.existingSecret .Values.frontend.secretEnv }}
{{- fail "frontend.existingSecret and frontend.secretEnv are mutually exclusive" }}
{{- end }}
{{- range $key := list "app.kubernetes.io/name" "app.kubernetes.io/instance" "app.kubernetes.io/component" }}
{{- if hasKey $.Values.podLabels $key }}
{{- fail (printf "podLabels may not override reserved selector label %s" $key) }}
{{- end }}
{{- end }}
{{- range $key := list "checksum/config" "checksum/secret" }}
{{- if hasKey $.Values.podAnnotations $key }}
{{- fail (printf "podAnnotations may not override reserved rollout annotation %s" $key) }}
{{- end }}
{{- end }}
{{- if and $isProduction (not .Values.api.existingSecret) }}
{{- fail "production requires api.existingSecret containing DATABASE_URL, JWT_SECRET, SECRET_ENCRYPTION_KEY, and the RECEIPT_SIGNING_* trust contract" }}
{{- end }}
{{- $allowedHosts := toString (default "" (get .Values.api.env "ALLOWED_HOSTS")) }}
{{- $forwardedAllowIps := toString (default "" (get .Values.api.env "FORWARDED_ALLOW_IPS")) }}
{{- if and $isProduction (or (not $allowedHosts) (contains "*" $allowedHosts)) }}
{{- fail "production api.env.ALLOWED_HOSTS must list exact ingress/API hostnames without wildcards" }}
{{- end }}
{{- if and $isProduction (or (not $forwardedAllowIps) (contains "*" $forwardedAllowIps) (eq $forwardedAllowIps "127.0.0.1")) }}
{{- fail "production api.env.FORWARDED_ALLOW_IPS must list deployment-specific trusted ingress proxy CIDRs; wildcard and loopback-only trust are forbidden" }}
{{- end }}
{{- if and .Values.migrations.enabled (not .Values.api.existingSecret) }}
{{- fail "migrations.enabled requires api.existingSecret because pre-install hooks cannot consume a chart-created Secret" }}
{{- end }}
{{- if and .Values.workers.document.enabled (not .Values.features.documents) }}
{{- fail "workers.document.enabled requires features.documents=true" }}
{{- end }}
{{- if and .Values.workers.reasoning.enabled (not .Values.features.reasoning) }}
{{- fail "workers.reasoning.enabled requires features.reasoning=true" }}
{{- end }}
{{- if and (or .Values.workers.document.enabled .Values.workers.reasoning.enabled) (not .Values.persistence.enabled) }}
{{- fail "standalone document/reasoning workers require persistence.enabled=true so API and workers share artifacts" }}
{{- end }}
{{- if and .Values.ingress.enabled (not .Values.ingress.host) }}
{{- fail "ingress.host is required when ingress.enabled=true" }}
{{- end }}
{{- if and .Values.ingress.tls.enabled (not .Values.ingress.tls.secretName) }}
{{- fail "ingress.tls.secretName is required when ingress.tls.enabled=true" }}
{{- end }}
{{- if .Values.frontend.autoscaling.enabled }}
{{- if not (hasKey .Values.frontend.resources.requests "cpu") }}
{{- fail "frontend autoscaling requires frontend.resources.requests.cpu" }}
{{- end }}
{{- if gt (int .Values.frontend.autoscaling.minReplicas) (int .Values.frontend.autoscaling.maxReplicas) }}
{{- fail "frontend.autoscaling.minReplicas must not exceed maxReplicas" }}
{{- end }}
{{- end }}
{{- $rwx := has "ReadWriteMany" .Values.persistence.accessModes }}
{{- $needsSharedStorage := or .Values.workers.document.enabled .Values.workers.reasoning.enabled }}
{{- if and .Values.persistence.enabled $needsSharedStorage (not $rwx) }}
{{- fail "persistence.accessModes must include ReadWriteMany when standalone artifact workers are enabled" }}
{{- end }}
{{- end }}
