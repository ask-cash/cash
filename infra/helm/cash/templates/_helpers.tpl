{{- define "cash.name" -}}
cash
{{- end -}}

{{- define "cash.labels" -}}
app.kubernetes.io/name: {{ include "cash.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{- define "cash.image" -}}
{{ .Values.image.repository }}:{{ .Values.image.tag }}
{{- end -}}

{{/*
Standard env for every role: ConfigMap (non-secret) + Secret (sensitive) +
the POD_NAME downward-api var the connector uses to derive its shard ordinal.
*/}}
{{- define "cash.envFrom" -}}
- configMapRef:
    name: {{ include "cash.name" . }}-config
- secretRef:
    name: {{ include "cash.name" . }}-secrets
{{- end -}}
