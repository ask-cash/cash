"""
app — Cloud-native runtime entrypoints for Cash.

Three roles share one container image, selected at launch:
  * gateway          — stateless FastAPI ingress (Telegram webhooks, health,
                       metrics, tenant onboarding). Scales horizontally.
  * worker           — consumes the job queue and runs the actual bot logic.
  * discord-connector — maintains Discord gateway sockets for a slice of
                       tenants and pushes events onto the queue.
  * cron             — one-shot scheduled fan-out jobs (briefings, email sweep).

Run: python -m app <role>
"""
