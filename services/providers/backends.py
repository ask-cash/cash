"""
backends.py — concrete LLM backends for services.providers.

Anthropic is the primary backend. An OpenAI-compatible backend is provided as a
fallback seam: it targets any ``/chat/completions`` endpoint (OpenAI, OpenRouter,
Ollama, …) selected purely by config, and stays dormant unless configured.

This is the ONLY module allowed to import a vendor LLM SDK.
"""

from __future__ import annotations

import logging
import os

from services.providers import register_backend

logger = logging.getLogger(__name__)


def _system_value(system: object, cache_system: bool):
    """Normalise the system field for the Anthropic SDK.

    - None            -> omit
    - list            -> pass through (already a structured/cache-controlled block)
    - str + cache      -> wrap in an ephemeral cache-control text block
    - str             -> pass as a plain string
    """
    if system is None:
        return None
    if isinstance(system, list):
        return system
    if cache_system:
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    return system


def anthropic_backend(cfg: dict, system: object, messages: list, cache_system: bool) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    kwargs: dict = {
        "model": cfg["model"],
        "max_tokens": cfg["max_tokens"],
        "messages": messages,
    }
    sys_val = _system_value(system, cache_system)
    if sys_val is not None:
        kwargs["system"] = sys_val
    if cfg.get("temperature") is not None:
        kwargs["temperature"] = cfg["temperature"]

    resp = client.messages.create(**kwargs)
    return resp.content[0].text


def _flatten_content(content) -> str:
    """Best-effort flatten of an Anthropic-style content list to plain text for
    OpenAI-style APIs (which take a string per message)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return str(content)


def openai_backend(cfg: dict, system: object, messages: list, cache_system: bool) -> str:
    """OpenAI-compatible chat-completions backend (fallback seam).

    Configured via ``OPENAI_API_KEY`` and optionally ``OPENAI_BASE_URL`` (defaults
    to OpenAI; point it at OpenRouter/Ollama/etc). Uses ``requests`` only, so no
    extra SDK dependency. Raises a clear error if selected without configuration.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "openai provider selected but OPENAI_API_KEY is not set — configure it "
            "or leave LLM_PROVIDER as 'anthropic'."
        )
    import requests

    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    oai_messages = []
    sys_text = None
    if isinstance(system, list):
        sys_text = _flatten_content(system)
    elif isinstance(system, str):
        sys_text = system
    if sys_text:
        oai_messages.append({"role": "system", "content": sys_text})
    for m in messages:
        oai_messages.append({"role": m.get("role", "user"), "content": _flatten_content(m.get("content", ""))})

    payload = {
        "model": cfg["model"],
        "max_tokens": cfg["max_tokens"],
        "messages": oai_messages,
    }
    if cfg.get("temperature") is not None:
        payload["temperature"] = cfg["temperature"]

    resp = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


register_backend("anthropic", anthropic_backend)
register_backend("openai", openai_backend)
