# Cash on Kubernetes

Multi-tenant deployment of Cash. One container image runs four roles, selected
by the launch arg: `gateway`, `worker`, `discord-connector`, `cron`.

```
Telegram ──webhook──▶ gateway (HPA) ──enqueue──▶ Redis Streams ──▶ worker (HPA) ──▶ Postgres (RLS) / GCS / Anthropic
Discord  ◀─gateway socket─▶ connector (StatefulSet) ──enqueue──▶ Redis
CronJobs ──fan-out per tenant──▶ Redis ──▶ worker
```

## 1. Provision infrastructure (Terraform)

```bash
cd infra/terraform
terraform init
terraform apply \
  -var project_id=my-gcp-project \
  -var uploads_bucket_name=my-cash-uploads
# note the outputs: get_credentials_command, uploads_bucket,
# workload_service_account, and *_secret names
$(terraform output -raw get_credentials_command)
```

This creates a GKE cluster (autoscaling node pool), Cloud SQL Postgres, a GCS
bucket, and Secret Manager entries for `DATABASE_URL` and
`SECRETS_ENCRYPTION_KEY`.

## 2. Install cluster add-ons

```bash
# Ingress + TLS
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace
helm install cert-manager jetstack/cert-manager -n cert-manager --create-namespace --set crds.enabled=true

# Autoscaling metrics (often preinstalled on GKE)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Queue-depth autoscaling for network-bound chat and transcription workers
helm install keda kedacore/keda -n keda --create-namespace

# Secret sync from Secret Manager
helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace

# Redis (acknowledged job queue): provision authenticated HA/managed Redis,
# then store its TLS URL in Secret Manager as `cash-redis-url`. Store its ACL
# username/password separately as `cash-redis-username` and
# `cash-redis-password` for KEDA. Never place credentials in a ConfigMap.

# Observability (Prometheus + Grafana, provides ServiceMonitor CRDs)
helm install kube-prom prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
```

Create a `ClusterSecretStore` named `gcp-secret-store` (referenced by
`values.yaml`) that points External Secrets at GCP Secret Manager, plus the
remaining secrets: `cash-redis-url`, `cash-anthropic-api-key`,
`cash-transcription-api-key`, `cash-telegram-webhook-secret`, and
`cash-admin-api-token`. Google sign-in/calendar also require
`cash-google-oauth-client-id` and `cash-google-oauth-client-secret`; KEDA
requires `cash-redis-username` and `cash-redis-password`.

## 3. Deploy Cash

```bash
helm upgrade --install cash infra/helm/cash -n cash \
  --set image.repository=ghcr.io/alg0-labs/cash \
  --set image.tag=v1.0.0 \
  --set client.image.repository=ghcr.io/alg0-labs/cash-client \
  --set client.image.tag=v1.0.0 \
  --set config.GCS_BUCKET="$(terraform -chdir=infra/terraform output -raw uploads_bucket)" \
  --set config.GCS_PROJECT=my-gcp-project \
  --set-string serviceAccount.annotations."iam\\.gke\\.io/gcp-service-account"="$(terraform -chdir=infra/terraform output -raw workload_service_account)" \
  --set worker.keda.enabled=true \
  --set-string worker.keda.address=redis.internal.example:6379 \
  --set config.PUBLIC_BASE_URL=https://api.cash.example.com \
  --set ingress.host=api.cash.example.com
```

CI/CD (`.github/workflows`) builds and pushes the image on tag, then runs the
same `helm upgrade` against the cluster.

## 4. Onboard a tenant

The admin API is intentionally not exposed by the public Ingress. Reach it
through an authenticated Kubernetes session:

```bash
kubectl -n cash port-forward service/cash-gateway 18080:80

curl -XPOST http://127.0.0.1:18080/admin/tenants \
  -H "X-Admin-Token: $ADMIN_API_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"display_name":"Suhail","telegram_bot_token":"<token>","owner_telegram_id":12345}'
```

The gateway registers the bot, stores its token encrypted, and calls Telegram
`setWebhook` to start delivery. The tenant connects Google/Gmail/Discord
through the usual `/connect_*` commands; those tokens land in the per-tenant
encrypted vault (`tenant_secrets`).

## Local development

`docker compose up --build` brings up the whole topology (gateway + worker +
connector against Postgres, Redis, minio). The legacy single-process bot
(`python main.py`) still works with SQLite + local files for quick iteration.

The Compose database bootstraps a separate, non-superuser `cash` application
role so PostgreSQL row-level tenant isolation is exercised locally. If the
`pgdata` volume was created by an older Compose file where `cash` was the
database superuser, back up anything you need and recreate that development
volume before relying on an RLS test; PostgreSQL superusers bypass RLS.

## Observability

Prometheus scrapes `GET /metrics` on the gateway and port `9000` on workers
(via ServiceMonitors).
Key series:

- `cash_webhook_requests_total{platform,status}` — inbound webhook volume/errors
- `cash_queue_depth` — backlog; scale workers if persistently high
- `cash_jobs_processed_total{type,status}` / `cash_job_duration_seconds`
- `cash_connector_sockets` — live Discord gateway connections per pod

Suggested alerts: queue depth sustained > N, job error ratio, connector socket
drops to zero on a shard.

## Secret rotation

- **Platform/OAuth tokens** live encrypted per tenant in `tenant_secrets`,
  re-written on refresh — rotating a tenant's bot token is a single
  `register_bot` call, no redeploy.
- **App-wide secrets** (DB URL, Fernet key, Anthropic key) live in cloud Secret
  Manager; External Secrets resyncs them hourly (`refreshInterval: 1h`).
  Environment variables are read only at process start, so restart workloads
  after the Kubernetes Secret refresh:

  ```bash
  kubectl -n cash rollout restart deployment/cash-gateway deployment/cash-worker
  kubectl -n cash rollout status deployment/cash-gateway
  kubectl -n cash rollout status deployment/cash-worker
  ```
- **`SECRETS_ENCRYPTION_KEY`** rotation requires re-encrypting `tenant_secrets`
  (decrypt with the old key, encrypt with the new) — do this with a one-off
  `cron`-style job before flipping the active key.
