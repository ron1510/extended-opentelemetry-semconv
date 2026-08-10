{{- define "servicegraph-indexer.arangoEnv" -}}
- name: SERVICEGRAPH_INDEXER_ARANGO_URLS
  value: {{ join "," .Values.arangodb.urls | quote }}
- name: SERVICEGRAPH_INDEXER_ARANGO_DATABASE
  value: {{ .Values.arangodb.database | quote }}
- name: SERVICEGRAPH_INDEXER_ARANGO_GRAPH
  value: {{ .Values.arangodb.graph | quote }}
- name: SERVICEGRAPH_INDEXER_ARANGO_VERIFY_TLS
  value: {{ .Values.arangodb.verifyTls | quote }}
- name: SERVICEGRAPH_INDEXER_ALLOW_DATABASE_CREATION
  value: {{ .Values.arangodb.allowDatabaseCreation | quote }}
- name: SERVICEGRAPH_INDEXER_CONNECTION_DEADLINE_SECONDS
  value: {{ .Values.arangodb.connectionDeadlineSeconds | quote }}
- name: SERVICEGRAPH_INDEXER_ARANGO_USERNAME
  valueFrom:
    secretKeyRef:
      name: {{ required "arangodb.auth.existingSecret is required" .Values.arangodb.auth.existingSecret | quote }}
      key: {{ .Values.arangodb.auth.usernameKey | quote }}
- name: SERVICEGRAPH_INDEXER_ARANGO_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.arangodb.auth.existingSecret | quote }}
      key: {{ .Values.arangodb.auth.passwordKey | quote }}
{{- end -}}
