{{- define "servicegraph-access.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "servicegraph-access.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 50 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "servicegraph-access.name" .) | trunc 50 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "servicegraph-access.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
app.kubernetes.io/name: {{ include "servicegraph-access.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: extended-otel-semconv
{{- end -}}

{{- define "servicegraph-access.projectorSelectorLabels" -}}
app.kubernetes.io/name: {{ include "servicegraph-access.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: projector
{{- end -}}

{{- define "servicegraph-access.apiSelectorLabels" -}}
app.kubernetes.io/name: {{ include "servicegraph-access.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: api
{{- end -}}

{{- define "servicegraph-access.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "servicegraph-access.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- required "serviceAccount.name is required when serviceAccount.create=false" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "servicegraph-access.image" -}}
{{- if .Values.image.digest -}}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag -}}
{{- end -}}
{{- end -}}
