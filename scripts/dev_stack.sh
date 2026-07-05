#!/usr/bin/env bash
#
# dev_stack.sh — Bring up and smoke-test the full Cash stack locally in Docker.
#
# Mirrors the production K8s topology: gateway + worker + discord-connector
# against Postgres (with RLS), Redis, and minio (S3). See docs/running.md.
#
# Usage:
#   ./scripts/dev_stack.sh up        # build + start the stack, wait for health
#   ./scripts/dev_stack.sh test      # run the unit suite inside a container
#   ./scripts/dev_stack.sh smoke     # hit gateway health/ready/metrics endpoints
#   ./scripts/dev_stack.sh onboard   # onboard a tenant (reads TG_TOKEN / TG_OWNER_ID)
#   ./scripts/dev_stack.sh logs      # tail logs for all services
#   ./scripts/dev_stack.sh down      # stop and remove the stack + volumes
#   ./scripts/dev_stack.sh all       # up -> test -> smoke (the common path)
#
# Env it reads:
#   ANTHROPIC_API_KEY   required for the worker to actually call Claude
#                       (compose interpolates it from your .env automatically)
#   TG_TOKEN            Telegram bot token, for `onboard`
#   TG_OWNER_ID         your Telegram numeric user id, for `onboard`
#   PUBLIC_BASE_URL     public HTTPS URL (ngrok/cloudflared) so Telegram can
#                       reach the gateway; needed for real Telegram delivery
set -euo pipefail

cd "$(dirname "$0")/.."

# Host gateway port — matches GATEWAY_PORT_HOST default in docker-compose.yml.
GATEWAY="http://localhost:${GATEWAY_PORT_HOST:-18080}"
ADMIN_TOKEN="dev-admin"   # matches docker-compose.yml ADMIN_API_TOKEN

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
blue()  { printf '\033[34m%s\033[0m\n' "$*"; }

require_docker() {
  if ! docker info >/dev/null 2>&1; then
    red "Docker daemon is not running. Start Docker Desktop and retry."
    exit 1
  fi
}

cmd_up() {
  require_docker
  blue "Building images and starting the stack..."
  docker compose up -d --build
  blue "Waiting for the gateway to become ready (Postgres + Redis up)..."
  for i in $(seq 1 60); do
    if curl -fsS "$GATEWAY/readyz" >/dev/null 2>&1; then
      green "Gateway ready at $GATEWAY"
      return 0
    fi
    sleep 2
  done
  red "Gateway did not become ready in time. Check: docker compose logs gateway"
  exit 1
}

cmd_test() {
  require_docker
  blue "Running the unit suite inside a one-off container (sqlite/pure, no infra)..."
  # --no-deps: tests don't need Postgres/Redis. --entrypoint python overrides the
  # image's `python -m app` entrypoint. Neutral env so nothing leaks in.
  docker compose run --rm --no-deps --entrypoint python \
    -e DATABASE_URL= -e ENFORCE_TENANT=false \
    worker -m unittest discover -s tests -v
  green "Unit suite passed."
}

cmd_smoke() {
  blue "GET /healthz"; curl -fsS "$GATEWAY/healthz"; echo
  blue "GET /readyz";  curl -fsS "$GATEWAY/readyz";  echo
  blue "GET /metrics (first lines)"; curl -fsS "$GATEWAY/metrics" | head -n 8
  green "Gateway smoke checks passed."
}

cmd_onboard() {
  : "${TG_TOKEN:?Set TG_TOKEN to your Telegram bot token}"
  : "${TG_OWNER_ID:?Set TG_OWNER_ID to your numeric Telegram user id}"
  blue "Onboarding tenant (registers bot, encrypts token, calls setWebhook if PUBLIC_BASE_URL set)..."
  curl -fsS -XPOST "$GATEWAY/admin/tenants" \
    -H "X-Admin-Token: $ADMIN_TOKEN" \
    -H 'content-type: application/json' \
    -d "{\"display_name\":\"Local Suhail\",\"telegram_bot_token\":\"$TG_TOKEN\",\"owner_telegram_id\":$TG_OWNER_ID}"
  echo
  green "Tenant onboarded. Message your Telegram bot to exercise the worker."
}

cmd_logs() { docker compose logs -f --tail=100; }
cmd_down() { docker compose down -v; green "Stack stopped, volumes removed."; }

case "${1:-all}" in
  up)      cmd_up ;;
  test)    cmd_test ;;
  smoke)   cmd_smoke ;;
  onboard) cmd_onboard ;;
  logs)    cmd_logs ;;
  down)    cmd_down ;;
  all)     cmd_up; cmd_test; cmd_smoke ;;
  *) echo "usage: $0 {up|test|smoke|onboard|logs|down|all}"; exit 2 ;;
esac
