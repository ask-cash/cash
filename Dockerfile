# syntax=docker/dockerfile:1

# ---- builder: install deps into a venv ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

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

# Default role is the gateway; override the command for worker / connector / cron.
#   gateway:           python -m app gateway
#   worker:            python -m app worker
#   discord-connector: python -m app discord-connector
#   cron:              python -m app cron <job_name>
EXPOSE 8080
ENTRYPOINT ["python", "-m", "app"]
CMD ["gateway"]
