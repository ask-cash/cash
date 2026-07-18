"""
providers — Cash's multi-provider LLM abstraction.

One entry point for every model call: ``send_message(call_site, ...)``. Feature
code names a **call site** (e.g. "owner_brain", "discord_proxy"), never a model
or an SDK, and a layered resolver decides provider + model + token budget:

    code defaults  →  tenant profile ("llm" settings)  →  per-call override

Anthropic is the primary backend; an OpenAI-compatible backend is registered as a
fallback seam. New backends register themselves via ``register_backend`` and
become selectable by config alone — no feature code changes.

The one place ``anthropic`` may be imported is a backend under this package.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Callable, Optional, Union

logger = logging.getLogger(__name__)

# Per-call-site code defaults. Models are named ONLY here (and in profile/env
# overrides), never in feature code.
DEFAULTS: dict[str, dict] = {
    "owner_brain":      {"model": "claude-sonnet-4-6", "max_tokens": 1000},
    "briefing":         {"model": "claude-sonnet-4-6", "max_tokens": 700},
    "file_answer":      {"model": "claude-sonnet-4-6", "max_tokens": 1500},
    "email_classifier": {"model": "claude-sonnet-4-6", "max_tokens": 800},
    "memory_reducer":   {"model": "claude-sonnet-4-6", "max_tokens": 800},
    "heartbeat":        {"model": "claude-sonnet-4-6", "max_tokens": 400},
    "discord_proxy":    {"model": "claude-haiku-4-5",  "max_tokens": 400},
    "directive_parser": {"model": "claude-haiku-4-5",  "max_tokens": 400},
    "identity_summary": {"model": "claude-haiku-4-5",  "max_tokens": 400},
    "composer":         {"model": "claude-haiku-4-5",  "max_tokens": 400},
    "routine_leaf":     {"model": "claude-haiku-4-5",  "max_tokens": 600},
    "routine_synthesis": {"model": "claude-sonnet-4-6", "max_tokens": 1200},
}

_FALLBACK_DEFAULT = {"model": "claude-sonnet-4-6", "max_tokens": 1000}

@dataclass(frozen=True)
class ProviderResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    stop_reason: str = ""


# Backends may return ProviderResult or a legacy string. Keeping the latter
# compatible lets local/test providers stay tiny while production providers
# expose usage for metering.
Backend = Callable[[dict, object, list, bool], Union[ProviderResult, str]]
_BACKENDS: dict[str, Backend] = {}


def register_backend(name: str, fn: Backend) -> None:
    _BACKENDS[name] = fn


def available_backends() -> list[str]:
    return sorted(_BACKENDS)


def _profile_llm() -> dict:
    """The tenant's optional ``llm`` config block, or {} (best-effort)."""
    try:
        from services.user_profile import load_profile
        return (load_profile() or {}).get("llm", {}) or {}
    except Exception:
        return {}


def resolve_config(call_site: str, **overrides) -> dict:
    """Merge the config layers for a call site (later layers win).

    Layers: code default → env (``LLM_PROVIDER``) → tenant profile ``llm`` (global
    provider/model + optional per-call ``call_sites``) → per-call overrides.
    Only non-None overrides apply, so callers pass just what they want to change.
    """
    cfg = dict(_FALLBACK_DEFAULT)
    cfg.update(DEFAULTS.get(call_site, {}))
    cfg["provider"] = os.getenv("LLM_PROVIDER", "anthropic")

    prof = _profile_llm()
    if prof:
        for key in ("provider", "model"):
            if prof.get(key):
                cfg[key] = prof[key]
        site_cfg = (prof.get("call_sites") or {}).get(call_site) or {}
        cfg.update({k: v for k, v in site_cfg.items() if v is not None})

    cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg


def send_message_result(
    call_site: str,
    *,
    system: object = None,
    messages: Optional[list] = None,
    user: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    provider: Optional[str] = None,
    cache_system: bool = False,
) -> ProviderResult:
    """Run one model call and return text plus provider-reported usage.

    Provide either ``messages`` (raw provider message list — needed for content
    blocks like an uploaded file) or ``user`` (a single user-turn string).
    ``system`` may be a plain string; set ``cache_system=True`` to send it as a
    cache-controlled block (preserving prompt caching on the composer paths).
    """
    cfg = resolve_config(
        call_site, model=model, max_tokens=max_tokens,
        temperature=temperature, provider=provider,
    )
    if messages is None:
        messages = [{"role": "user", "content": user if user is not None else ""}]

    backend = _BACKENDS.get(cfg["provider"])
    if backend is None:
        raise ValueError(
            f"unknown LLM provider {cfg['provider']!r} for call site {call_site!r}; "
            f"available: {available_backends()}"
        )
    raw = backend(cfg, system, messages, cache_system)
    if isinstance(raw, ProviderResult):
        return raw
    return ProviderResult(text=str(raw), model=str(cfg.get("model") or ""))


def send_message(
    call_site: str,
    *,
    system: object = None,
    messages: Optional[list] = None,
    user: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    provider: Optional[str] = None,
    cache_system: bool = False,
) -> str:
    """Backward-compatible text-only wrapper around :func:`send_message_result`."""
    return send_message_result(
        call_site,
        system=system,
        messages=messages,
        user=user,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        provider=provider,
        cache_system=cache_system,
    ).text


# The model catalog (providers × models + metadata) — the data companion callers
# and any config UI pick a concrete provider/model from.
from services.providers.catalog import (  # noqa: E402,F401
    CatalogModel,
    MODELS_BY_PROVIDER,
    DEFAULT_MODEL_BY_PROVIDER,
    PROVIDER_DISPLAY_NAMES,
    PROVIDER_SUPPORTS_PLATFORM_AUTH,
    MANAGED_MODELS,
    provider_ids,
    get_models_for_provider,
    get_default_model_for_provider,
    provider_display_name,
    provider_supports_platform_auth,
    find_model,
    is_known_model,
)

# Register the built-in backends (Anthropic primary + OpenAI-compatible seam).
from services.providers import backends as _backends  # noqa: E402,F401
