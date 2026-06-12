# Cash on Kubernetes

Multi-tenant deployment of Cash. One container image runs four roles, selected
by the launch arg: `gateway`, `worker`, `discord-connector`, `cron`.

```
Telegram ──webhook──▶ gateway (HPA) ──enqueue──▶ Redis ──▶ worker (HPA) ──▶ Postgres (RLS) / S3 / Anthropic
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
# note the outputs: get_credentials_command, *_secret names
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

# Secret sync from Secret Manager
helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace

# Redis (job queue)
helm install cash-redis bitnami/redis -n cash --create-namespace --set auth.enabled=false

# Observability (Prometheus + Grafana, provides ServiceMonitor CRDs)
helm install kube-prom prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
```

Create a `ClusterSecretStore` named `gcp-secret-store` (referenced by
`values.yaml`) that points External Secrets at GCP Secret Manager, plus the
remaining secrets: `cash-anthropic-api-key`, `cash-telegram-webhook-secret`,
`cash-admin-api-token`.

## 3. Deploy Cash

```bash
helm upgrade --install cash infra/helm/cash -n cash \
  --set image.repository=ghcr.io/alg0-labs/cash \
  --set image.tag=v1.0.0 \
  --set config.PUBLIC_BASE_URL=https://api.cash.example.com \
  --set ingress.host=api.cash.example.com
```

CI/CD (`.github/workflows`) builds and pushes the image on tag, then runs the
same `helm upgrade` against the cluster.

## 4. Onboard a tenant

```bash
curl -XPOST https://api.cash.example.com/admin/tenants \
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

## Observability

Prometheus scrapes `GET /metrics` on the gateway (via the ServiceMonitor).
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
  Manager; External Secrets resyncs them hourly (`refreshInterval: 1h`), so
  rotating the source value rolls out without editing the chart.
- **`SECRETS_ENCRYPTION_KEY`** rotation requires re-encrypting `tenant_secrets`
  (decrypt with the old key, encrypt with the new) — do this with a one-off
  `cron`-style job before flipping the active key.
