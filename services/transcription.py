"""Provider-neutral speech transcription for dashboard voice and audio media."""

from __future__ import annotations

import os
import subprocess
import math
from pathlib import Path

import requests


class TranscriptionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "transcription_failed",
        status_code: int = 502,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _api_key() -> str:
    return (
        os.getenv("TRANSCRIPTION_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    ).strip()


def is_configured() -> bool:
    return bool(_api_key())


def max_seconds() -> int:
    return _positive_int("VOICE_MAX_SECONDS", 90)


def max_bytes(plan: str = "free") -> int:
    default = 8 * 1024 * 1024 if (plan or "free").lower() == "free" else 15 * 1024 * 1024
    return _positive_int("VOICE_MAX_BYTES", default)


def media_duration_seconds(path: str) -> float:
    """Read container duration with ffprobe without decoding untrusted media."""
    try:
        completed = subprocess.run(
            [
                os.getenv("FFPROBE_PATH", "ffprobe"),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=_positive_int("MEDIA_PROBE_TIMEOUT_SECONDS", 10),
        )
        duration = float(completed.stdout.strip())
    except FileNotFoundError as exc:
        raise TranscriptionError(
            "Media inspection is not available on this server.",
            code="media_inspection_unavailable",
            status_code=503,
        ) from exc
    except (subprocess.SubprocessError, ValueError) as exc:
        raise TranscriptionError(
            "That audio or video file could not be inspected.",
            code="invalid_media",
            status_code=415,
        ) from exc
    if not math.isfinite(duration) or duration <= 0:
        raise TranscriptionError(
            "That audio or video file has no valid duration.",
            code="invalid_media",
            status_code=415,
        )
    return duration


def validate_media_duration(path: str) -> float:
    duration = media_duration_seconds(path)
    limit = max_seconds()
    if duration > limit + 0.25:
        raise TranscriptionError(
            f"Audio and video can be up to {limit} seconds long.",
            code="media_too_long",
            status_code=413,
        )
    return duration


def transcribe_path(path: str, *, filename: str = "recording.webm", mime_type: str = "") -> str:
    """Transcribe an already validated local media file.

    The key and endpoint are independently configurable so deployments can use
    an OpenAI-compatible transcription gateway without changing application
    code.
    """
    api_key = _api_key()
    if not api_key:
        raise TranscriptionError(
            "Voice transcription is not configured. Set TRANSCRIPTION_API_KEY "
            "or OPENAI_API_KEY on the gateway and worker."
        )
    endpoint = os.getenv(
        "TRANSCRIPTION_API_URL",
        "https://api.openai.com/v1/audio/transcriptions",
    ).strip()
    model = os.getenv("TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe").strip()
    timeout = _positive_int("TRANSCRIPTION_TIMEOUT_SECONDS", 120)

    safe_name = Path(filename or "recording.webm").name
    try:
        with open(path, "rb") as source:
            response = requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": model, "response_format": "json"},
                files={
                    "file": (
                        safe_name,
                        source,
                        mime_type or "application/octet-stream",
                    )
                },
                timeout=timeout,
            )
        response.raise_for_status()
        payload = response.json()
    except requests.Timeout as exc:
        raise TranscriptionError("Voice transcription timed out. Please try a shorter recording.") from exc
    except (requests.RequestException, ValueError) as exc:
        raise TranscriptionError("Voice transcription failed. Please try again.") from exc

    text = (payload.get("text") or "").strip() if isinstance(payload, dict) else ""
    if not text:
        raise TranscriptionError("No speech was detected in that recording.")
    return text
