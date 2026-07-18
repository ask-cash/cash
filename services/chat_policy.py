"""Server-owned dashboard chat entitlements and context accounting.

The browser receives these capabilities for presentation, but this module is
also called on every mutation.  A modified client therefore cannot bypass
model, context, upload, or request limits.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Iterable

from services.providers.catalog import MANAGED_MODELS, CatalogModel, find_model

PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_ENTERPRISE = "enterprise"
_PLAN_ORDER = {PLAN_FREE: 0, PLAN_PRO: 1, PLAN_ENTERPRISE: 2}

DEFAULT_FREE_MODEL = "claude-haiku-4-5-20251001"


class ChatPolicyError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_request", status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class ContextState:
    used_tokens: int
    limit_tokens: int
    remaining_tokens: int
    estimated: bool = True
    truncated: bool = False

    def as_dict(self) -> dict:
        return {
            "usedTokens": self.used_tokens,
            "limitTokens": self.limit_tokens,
            "remainingTokens": self.remaining_tokens,
            "estimated": self.estimated,
            "truncated": self.truncated,
        }


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def normalize_plan(plan: str | None) -> str:
    candidate = (plan or PLAN_FREE).strip().lower()
    return candidate if candidate in _PLAN_ORDER else PLAN_FREE


def _configured_free_models() -> set[str]:
    raw = os.getenv("FREE_CHAT_MODELS", DEFAULT_FREE_MODEL).strip()
    if raw == "*":
        return {m.id for m in MANAGED_MODELS}
    return {part.strip() for part in raw.split(",") if part.strip()}


def required_plan(model_id: str) -> str:
    return PLAN_FREE if model_id in _configured_free_models() else PLAN_PRO


def plan_allows_model(plan: str, model_id: str) -> bool:
    return _PLAN_ORDER[normalize_plan(plan)] >= _PLAN_ORDER[required_plan(model_id)]


def default_model_id(plan: str) -> str:
    configured = os.getenv("DEFAULT_DASHBOARD_MODEL", DEFAULT_FREE_MODEL).strip()
    if find_model(configured, "anthropic") and plan_allows_model(plan, configured):
        return configured
    for model in reversed(MANAGED_MODELS):
        if plan_allows_model(plan, model.id):
            return model.id
    return DEFAULT_FREE_MODEL


def require_model(plan: str, model_id: str | None) -> CatalogModel:
    chosen = (model_id or default_model_id(plan)).strip()
    model = find_model(chosen, "anthropic")
    if model is None or model not in MANAGED_MODELS:
        raise ChatPolicyError(
            "That Claude model is not available in dashboard chat.",
            code="unknown_model",
        )
    if not plan_allows_model(plan, chosen):
        raise ChatPolicyError(
            f"{model.display_name} requires a Pro plan.",
            code="model_not_entitled",
            status_code=403,
        )
    return model


def context_limit(plan: str, model: CatalogModel | str) -> int:
    if isinstance(model, str):
        found = find_model(model, "anthropic")
        if found is None:
            raise ChatPolicyError("Unknown model.", code="unknown_model")
        model = found
    plan = normalize_plan(plan)
    if plan == PLAN_FREE:
        plan_limit = _positive_int("FREE_CHAT_CONTEXT_TOKENS", 32_000)
    elif plan == PLAN_PRO:
        plan_limit = _positive_int("PRO_CHAT_CONTEXT_TOKENS", 200_000)
    else:
        plan_limit = _positive_int(
            "ENTERPRISE_CHAT_CONTEXT_TOKENS", model.context_window_tokens
        )
    return min(plan_limit, model.context_window_tokens)


def estimate_tokens(value: str | bytes | None) -> int:
    """Conservative provider-neutral estimate used for trimming and the UI."""
    if value is None:
        return 0
    if isinstance(value, bytes):
        if not value:
            return 0
        # Base64/document tokenisation varies; bytes/3 errs on the safe side.
        return max(1, math.ceil(len(value) / 3))
    if not value:
        return 0
    # Claude English text is often near four chars/token. 3.5 is safer across
    # code, JSON, punctuation, and non-English text.
    return max(1, math.ceil(len(value.encode("utf-8")) / 3.5))


def estimate_attachment_tokens(attachment: dict) -> int:
    transcript = attachment.get("transcript") or ""
    if transcript:
        return estimate_tokens(transcript)
    mime = (attachment.get("mimeType") or attachment.get("mime_type") or "").lower()
    size = int(attachment.get("sizeBytes") or attachment.get("size_bytes") or 0)
    if mime.startswith("image/"):
        # A high-resolution image is commonly in the low-thousands of tokens.
        return min(4_000, max(800, math.ceil(size / 1_500)))
    if mime == "application/pdf":
        return min(24_000, max(1_000, math.ceil(size / 3)))
    if mime.startswith("text/") or mime in {"application/json", "application/xml"}:
        return min(50_000, max(1, math.ceil(size / 3.5)))
    return 256


def estimate_message_tokens(message: dict) -> int:
    total = estimate_tokens(message.get("content") or "") + 8
    for attachment in message.get("attachments") or []:
        total += estimate_attachment_tokens(attachment)
    return total


def _history_line(message: dict) -> str:
    role = "User" if message.get("role") == "user" else "Cash"
    content = (message.get("content") or "").strip()
    attachments = message.get("attachments") or []
    refs = []
    for item in attachments:
        name = item.get("name") or "attachment"
        transcript = (item.get("transcript") or "").strip()
        if transcript:
            refs.append(f"{name} transcript: {transcript[:12_000]}")
        else:
            refs.append(f"attached file: {name}")
    suffix = f"\n[{'; '.join(refs)}]" if refs else ""
    return f"{role}: {content}{suffix}".strip()


def assemble_history(
    messages: Iterable[dict],
    *,
    limit_tokens: int,
    current_text: str = "",
    current_attachments: Iterable[dict] = (),
    prompt_reserve_tokens: int | None = None,
) -> tuple[str, ContextState]:
    """Select the newest complete turns that fit the effective context window."""
    reserve = prompt_reserve_tokens or _positive_int("CHAT_PROMPT_RESERVE_TOKENS", 6_000)
    current = estimate_tokens(current_text) + sum(
        estimate_attachment_tokens(a) for a in current_attachments
    )
    output_reserve = _positive_int("CHAT_OUTPUT_RESERVE_TOKENS", 2_000)
    available = max(0, limit_tokens - reserve - output_reserve - current)
    if current + reserve + output_reserve > limit_tokens:
        raise ChatPolicyError(
            "This message and its attachments are larger than your available context window.",
            code="context_limit_exceeded",
            status_code=413,
        )

    materialized = list(messages)
    total_history = sum(estimate_message_tokens(m) for m in materialized)
    selected: list[str] = []
    selected_tokens = 0
    for message in reversed(materialized):
        cost = estimate_message_tokens(message)
        if cost > available - selected_tokens:
            break
        selected.append(_history_line(message))
        selected_tokens += cost
    selected.reverse()

    used = min(limit_tokens, reserve + current + selected_tokens)
    state = ContextState(
        used_tokens=used,
        limit_tokens=limit_tokens,
        remaining_tokens=max(0, limit_tokens - used),
        truncated=selected_tokens < total_history,
    )
    return "\n\n".join(selected) if selected else "(No earlier turns.)", state


def context_state(messages: Iterable[dict], plan: str, model_id: str) -> ContextState:
    model = require_model(plan, model_id)
    limit = context_limit(plan, model)
    _, state = assemble_history(messages, limit_tokens=limit)
    return state


def model_view(model: CatalogModel, plan: str) -> dict:
    needed = required_plan(model.id)
    return {
        "id": model.id,
        "displayName": model.display_name,
        "contextWindowTokens": model.context_window_tokens,
        "maxOutputTokens": model.max_output_tokens,
        "supportsThinking": model.supports_thinking,
        "available": plan_allows_model(plan, model.id),
        "requiredPlan": None if needed == PLAN_FREE else needed,
    }


def capabilities(plan: str) -> dict:
    from services import attachments, transcription

    plan = normalize_plan(plan)
    default = default_model_id(plan)
    selected = require_model(plan, default)
    return {
        "models": [model_view(model, plan) for model in MANAGED_MODELS],
        "defaultModelId": default,
        "plan": {"id": plan, "label": plan.title()},
        "contextLimitTokens": context_limit(plan, selected),
        "attachmentLimits": {
            "maxFiles": attachments.max_files_per_message(),
            "maxBytes": attachments.max_file_bytes(plan),
            "maxImageBytes": attachments.max_provider_image_bytes(),
            "maxPdfPages": attachments.max_pdf_pages(plan),
            "maxTotalBytes": attachments.max_total_bytes_per_message(plan),
            "acceptedTypes": [
                mime for mime in attachments.accepted_client_types()
                if transcription.is_configured()
                or not attachments.is_audio_or_video(mime)
            ],
        },
        "voice": {
            "enabled": transcription.is_configured(),
            "reason": None if transcription.is_configured() else "not_configured",
            "maxSeconds": transcription.max_seconds(),
            "maxBytes": transcription.max_bytes(plan),
        },
    }
