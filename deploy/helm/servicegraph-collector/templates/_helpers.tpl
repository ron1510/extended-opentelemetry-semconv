{{- define "servicegraph-collector.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "servicegraph-collector.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 40 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "servicegraph-collector.name" .) | trunc 40 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "servicegraph-collector.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "servicegraph-collector.labels" -}}
helm.sh/chart: {{ include "servicegraph-collector.chart" . }}
app.kubernetes.io/name: {{ include "servicegraph-collector.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: extended-otel-semconv
{{- end -}}

{{- define "servicegraph-collector.selectorLabels" -}}
app.kubernetes.io/name: {{ include "servicegraph-collector.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "servicegraph-collector.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "servicegraph-collector.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- required "serviceAccount.name is required when serviceAccount.create=false" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "servicegraph-collector.image" -}}
{{- if .Values.image.digest -}}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag -}}
{{- end -}}
{{- end -}}
