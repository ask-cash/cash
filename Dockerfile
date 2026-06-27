# syntax=docker/dockerfile:1

# ---- builder: install deps into a venv ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

# Build tooling for any sdist that needs compiling; confined to the builder
# stage so the runtime image stays slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
# --timeout / --retries keep the build resilient to flaky PyPI connections so a
# single dropped download doesn't fail the whole image build.
RUN pip install --upgrade pip \
    && pip install --timeout 120 --retries 10 -r requirements.txt

# ---- runtime: copy venv + source ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root user
RUN useradd --create-home --uid 10001 cash

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . .
RUN chown -R cash:cash /app

USER cash

# Default role is the gateway; override the command for the other roles.
#   gateway:           python -m app gateway
#   worker:            python -m app worker
#   discord-connector: python -m app discord-connector
#   telegram-poller:   python -m app telegram-poller   (long-poll, no webhook)
#   cron:              python -m app cron <job_name>
EXPOSE 8080
ENTRYPOINT ["python", "-m", "app"]
CMD ["gateway"]
