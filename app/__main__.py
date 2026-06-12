"""
Entrypoint dispatcher: `python -m app <role> [args]`.

Roles:
  gateway            -> uvicorn server for app.gateway:app
  worker             -> queue consumer (app.worker)
  discord-connector  -> Discord gateway pool (app.discord_connector)
  cron <job_name>    -> fan out a scheduled job to all tenants (app.cron)
"""

import sys

from services.config import settings


def _run_gateway() -> None:
    import uvicorn

    uvicorn.run(
        "app.gateway:app",
        host=settings.gateway_host,
        port=settings.gateway_port,
        log_level=settings.log_level.lower(),
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m app <gateway|worker|discord-connector|cron <job>>")
        raise SystemExit(2)

    role = sys.argv[1]
    if role == "gateway":
        _run_gateway()
    elif role == "worker":
        from app.worker import main as worker_main

        worker_main()
    elif role == "discord-connector":
        from app.discord_connector import main as connector_main

        connector_main()
    elif role == "cron":
        if len(sys.argv) < 3:
            print("usage: python -m app cron <job_name>")
            raise SystemExit(2)
        from app.cron import fan_out

        fan_out(sys.argv[2])
    else:
        print(f"unknown role: {role}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
