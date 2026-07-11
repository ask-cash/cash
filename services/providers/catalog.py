"""
catalog.py — Cash's LLM provider/model catalog.

For each provider, the models Cash can be pointed at, with the metadata the
abstraction and any config UI need (context window, max output, thinking
support). This is the data companion to ``services.providers.send_message``:
feature code names a *call site*, and this is where a profile/dashboard picks the
concrete provider + model from. Pricing/vision/caching fields are intentionally
omitted — Cash doesn't use them yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CatalogModel:
    id: str
    display_name: str
    context_window_tokens: int
    default_context_window_tokens: int
    max_output_tokens: int
    supports_thinking: bool = False
    adaptive_thinking_only: bool = False
    long_context_pricing_threshold_tokens: Optional[int] = None


def _m(id, display_name, ctx, default_ctx, max_out,
       supports_thinking=False, adaptive_thinking_only=False,
       long_context_pricing_threshold_tokens=None) -> CatalogModel:
    return CatalogModel(
        id=id,
        display_name=display_name,
        context_window_tokens=ctx,
        default_context_window_tokens=default_ctx,
        max_output_tokens=max_out,
        supports_thinking=supports_thinking,
        adaptive_thinking_only=adaptive_thinking_only,
        long_context_pricing_threshold_tokens=long_context_pricing_threshold_tokens,
    )


MODELS_BY_PROVIDER: dict[str, tuple[CatalogModel, ...]] = {
    "anthropic": (
        _m("claude-fable-5", "Claude Fable 5", 1_000_000, 200_000, 128_000,
           supports_thinking=True, adaptive_thinking_only=True,
           long_context_pricing_threshold_tokens=200_000),
        _m("claude-opus-4-8", "Claude Opus 4.8", 1_000_000, 200_000, 128_000,
           supports_thinking=True, long_context_pricing_threshold_tokens=200_000),
        _m("claude-opus-4-7", "Claude Opus 4.7", 1_000_000, 200_000, 128_000,
           supports_thinking=True, long_context_pricing_threshold_tokens=200_000),
        _m("claude-opus-4-6", "Claude Opus 4.6", 1_000_000, 200_000, 128_000,
           supports_thinking=True, long_context_pricing_threshold_tokens=200_000),
        _m("claude-sonnet-5", "Claude Sonnet 5", 1_000_000, 200_000, 128_000,
           supports_thinking=True, long_context_pricing_threshold_tokens=200_000),
        _m("claude-sonnet-4-6", "Claude Sonnet 4.6", 1_000_000, 200_000, 64_000,
           supports_thinking=True, long_context_pricing_threshold_tokens=200_000),
        _m("claude-sonnet-4-5-20250929", "Claude Sonnet 4.5", 200_000, 200_000, 64_000,
           supports_thinking=True),
        _m("claude-opus-4-5-20251101", "Claude Opus 4.5", 200_000, 200_000, 64_000,
           supports_thinking=True),
        _m("claude-haiku-4-5-20251001", "Claude Haiku 4.5", 200_000, 200_000, 64_000,
           supports_thinking=True),
    ),
    "openai": (
        _m("gpt-5.5", "GPT-5.5", 1_050_000, 200_000, 128_000,
           supports_thinking=True, long_context_pricing_threshold_tokens=272_000),
        _m("gpt-5.5-pro", "GPT-5.5 Pro", 1_050_000, 200_000, 128_000,
           supports_thinking=True, long_context_pricing_threshold_tokens=272_000),
        _m("gpt-5.4", "GPT-5.4", 1_050_000, 200_000, 128_000,
           supports_thinking=True, long_context_pricing_threshold_tokens=272_000),
        _m("gpt-5.2", "GPT-5.2", 400_000, 200_000, 128_000, supports_thinking=True),
        _m("gpt-5.4-mini", "GPT-5.4 Mini", 400_000, 200_000, 128_000, supports_thinking=True),
        _m("gpt-5.4-nano", "GPT-5.4 Nano", 400_000, 200_000, 128_000, supports_thinking=True),
    ),
    "gemini": (
        _m("gemini-3.5-flash", "Gemini 3.5 Flash", 1_048_576, 200_000, 65_536, supports_thinking=True),
        _m("gemini-3.1-pro-preview", "Gemini 3.1 Pro Preview", 1_048_576, 200_000, 65_536,
           supports_thinking=True, long_context_pricing_threshold_tokens=200_000),
        _m("gemini-3.1-pro-preview-customtools", "Gemini 3.1 Pro Preview (Custom Tools)",
           1_048_576, 200_000, 65_536, supports_thinking=True,
           long_context_pricing_threshold_tokens=200_000),
        _m("gemini-3-flash-preview", "Gemini 3 Flash Preview", 1_048_576, 200_000, 65_536,
           supports_thinking=True),
        _m("gemini-3.1-flash-lite-preview", "Gemini 3.1 Flash-Lite Preview", 1_048_576, 200_000,
           65_536, supports_thinking=True),
        _m("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", 1_048_576, 200_000, 65_536,
           supports_thinking=True),
        _m("gemini-2.5-flash", "Gemini 2.5 Flash", 1_000_000, 200_000, 65_536, supports_thinking=True),
        _m("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite", 1_000_000, 200_000, 65_536),
        _m("gemini-2.5-pro", "Gemini 2.5 Pro", 1_048_576, 200_000, 65_536,
           supports_thinking=True, long_context_pricing_threshold_tokens=200_000),
    ),
    "ollama": (
        _m("llama3.2", "Llama 3.2", 128_000, 128_000, 4_096),
        _m("mistral", "Mistral", 32_768, 32_768, 4_096),
    ),
    "fireworks": (
        _m("accounts/fireworks/models/kimi-k2p6", "Kimi K2.6", 262_144, 200_000, 32_768,
           supports_thinking=True),
        _m("accounts/fireworks/models/glm-5p2", "GLM 5.2", 1_040_000, 200_000, 131_072,
           supports_thinking=True),
        _m("accounts/fireworks/models/kimi-k2p5", "Kimi K2.5", 256_000, 200_000, 32_768),
        _m("accounts/fireworks/models/minimax-m3", "MiniMax M3", 524_288, 200_000, 512_000,
           supports_thinking=True),
        _m("accounts/fireworks/models/minimax-m2p7", "MiniMax M2.7", 196_608, 196_608, 25_000),
        _m("accounts/fireworks/models/minimax-m2p5", "MiniMax M2.5", 196_608, 196_608, 25_000),
        _m("accounts/fireworks/models/deepseek-v4-pro", "DeepSeek V4 Pro", 1_040_000, 200_000,
           131_072, supports_thinking=True),
        _m("accounts/fireworks/models/deepseek-v4-flash", "DeepSeek V4 Flash", 1_040_000, 200_000,
           131_072, supports_thinking=True),
    ),
    "together": (
        _m("MiniMaxAI/MiniMax-M3", "MiniMax M3", 524_288, 200_000, 512_000, supports_thinking=True),
    ),
    "openrouter": (
        _m("anthropic/claude-fable-5", "Claude Fable 5", 1_000_000, 200_000, 128_000,
           supports_thinking=True, adaptive_thinking_only=True,
           long_context_pricing_threshold_tokens=200_000),
        _m("anthropic/claude-opus-4.8", "Claude Opus 4.8", 1_000_000, 200_000, 128_000,
           supports_thinking=True, long_context_pricing_threshold_tokens=200_000),
        _m("anthropic/claude-opus-4.7", "Claude Opus 4.7", 1_000_000, 200_000, 128_000,
           supports_thinking=True, long_context_pricing_threshold_tokens=200_000),
        _m("anthropic/claude-opus-4.6", "Claude Opus 4.6", 1_000_000, 200_000, 128_000,
           supports_thinking=True, long_context_pricing_threshold_tokens=200_000),
        _m("anthropic/claude-sonnet-5", "Claude Sonnet 5", 1_000_000, 200_000, 128_000,
           supports_thinking=True, long_context_pricing_threshold_tokens=200_000),
        _m("anthropic/claude-sonnet-4.6", "Claude Sonnet 4.6", 1_000_000, 200_000, 64_000,
           supports_thinking=True, long_context_pricing_threshold_tokens=200_000),
        _m("anthropic/claude-sonnet-4.5", "Claude Sonnet 4.5", 200_000, 200_000, 64_000,
           supports_thinking=True),
        _m("anthropic/claude-opus-4.5", "Claude Opus 4.5", 200_000, 200_000, 64_000,
           supports_thinking=True),
        _m("anthropic/claude-haiku-4.5", "Claude Haiku 4.5", 200_000, 200_000, 64_000,
           supports_thinking=True),
        _m("x-ai/grok-4.20-beta", "Grok 4.20 Beta", 256_000, 200_000, 16_000, supports_thinking=True),
        _m("x-ai/grok-4.3", "Grok 4.3", 1_000_000, 200_000, 16_000, supports_thinking=True),
        _m("x-ai/grok-4", "Grok 4", 131_072, 131_072, 16_000, supports_thinking=True),
        _m("deepseek/deepseek-r1-0528", "DeepSeek R1", 163_840, 163_840, 32_000, supports_thinking=True),
        _m("deepseek/deepseek-chat-v3-0324", "DeepSeek V3", 163_840, 163_840, 32_000),
        _m("deepseek/deepseek-v4-pro", "DeepSeek V4 Pro", 1_048_576, 200_000, 384_000,
           supports_thinking=True),
        _m("deepseek/deepseek-v4-flash", "DeepSeek V4 Flash", 1_048_576, 200_000, 384_000,
           supports_thinking=True),
        _m("deepseek/deepseek-v3.2-speciale", "DeepSeek V3.2 Speciale", 163_840, 163_840, 163_840,
           supports_thinking=True),
        _m("qwen/qwen3.5-plus-02-15", "Qwen 3.5 Plus", 131_072, 131_072, 8_192, supports_thinking=True),
        _m("qwen/qwen3.5-397b-a17b", "Qwen 3.5 397B", 131_072, 131_072, 8_192, supports_thinking=True),
        _m("qwen/qwen3.5-flash-02-23", "Qwen 3.5 Flash", 131_072, 131_072, 8_192),
        _m("qwen/qwen3-coder-next", "Qwen 3 Coder", 131_072, 131_072, 8_192),
        _m("moonshotai/kimi-k2.6", "Kimi K2.6", 262_144, 200_000, 32_768, supports_thinking=True),
        _m("moonshotai/kimi-k2.5", "Kimi K2.5", 256_000, 200_000, 32_768),
        _m("minimax/minimax-m3", "MiniMax M3", 524_288, 200_000, 512_000, supports_thinking=True),
        _m("minimax/minimax-m2.7", "MiniMax M2.7", 196_608, 196_608, 131_072, supports_thinking=True),
        _m("minimax/minimax-m2.5", "MiniMax M2.5", 196_608, 196_608, 196_608, supports_thinking=True),
        _m("minimax/minimax-m2.1", "MiniMax M2.1", 196_608, 196_608, 196_608, supports_thinking=True),
        _m("minimax/minimax-m2", "MiniMax M2", 196_608, 196_608, 196_608, supports_thinking=True),
        _m("minimax/minimax-m2-her", "MiniMax M2-her", 65_536, 65_536, 2_048),
        _m("minimax/minimax-m1", "MiniMax M1", 1_000_000, 200_000, 40_000, supports_thinking=True),
        _m("minimax/minimax-01", "MiniMax-01", 1_000_000, 200_000, 1_000_000),
        _m("z-ai/glm-5.2", "GLM-5.2", 1_048_576, 200_000, 131_072, supports_thinking=True),
        _m("mistralai/mistral-medium-3", "Mistral Medium 3", 131_072, 131_072, 16_000),
        _m("mistralai/mistral-small-2603", "Mistral Small 4", 131_072, 131_072, 16_000),
        _m("mistralai/devstral-2512", "Devstral 2", 131_072, 131_072, 16_000),
        _m("meta-llama/llama-4-maverick", "Llama 4 Maverick", 1_000_000, 200_000, 16_000),
        _m("meta-llama/llama-4-scout", "Llama 4 Scout", 327_680, 200_000, 16_000),
        _m("amazon/nova-pro-v1", "Amazon Nova Pro", 300_000, 200_000, 5_000),
        _m("openrouter/owl-alpha", "Owl Alpha", 1_048_576, 200_000, 262_144),
    ),
    "minimax": (
        _m("MiniMax-M3", "MiniMax M3", 1_000_000, 200_000, 512_000, supports_thinking=True),
        _m("MiniMax-M2.7", "MiniMax M2.7", 200_000, 200_000, 16_384, supports_thinking=True),
    ),
    "atlascloud": (
        _m("deepseek-ai/deepseek-v4-pro", "DeepSeek V4 Pro", 128_000, 128_000, 8_192,
           supports_thinking=True),
    ),
    "openai-compatible": (),
}


DEFAULT_MODEL_BY_PROVIDER: dict[str, str] = {
    "anthropic": "claude-opus-4-8",
    "openai": "gpt-5.5",
    "gemini": "gemini-2.5-flash",
    "ollama": "llama3.2",
    "fireworks": "accounts/fireworks/models/kimi-k2p5",
    "together": "MiniMaxAI/MiniMax-M3",
    "openrouter": "x-ai/grok-4.20-beta",
    "minimax": "MiniMax-M2.7",
    "atlascloud": "deepseek-ai/deepseek-v4-pro",
    "openai-compatible": "",
}


PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
    "ollama": "Ollama",
    "fireworks": "Fireworks",
    "together": "Together AI",
    "openrouter": "OpenRouter",
    "openai-compatible": "OpenAI-compatible",
    "minimax": "MiniMax",
    "atlascloud": "Atlas Cloud",
}


# Whether each provider supports platform-managed auth (a hosted proxy route).
# Missing entries are treated as False.
PROVIDER_SUPPORTS_PLATFORM_AUTH: dict[str, bool] = {
    "anthropic": True,
    "openai": True,
    "gemini": True,
    "ollama": False,
    "fireworks": True,
    "together": True,
    "openrouter": False,
    "openai-compatible": False,
    "minimax": False,
    "atlascloud": False,
}


# Anthropic is Cash's managed provider today.
MANAGED_MODELS = MODELS_BY_PROVIDER["anthropic"]


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def provider_ids() -> list[str]:
    return list(MODELS_BY_PROVIDER.keys())


def get_models_for_provider(provider: str) -> tuple[CatalogModel, ...]:
    return MODELS_BY_PROVIDER.get(provider, ())


def get_default_model_for_provider(provider: str) -> Optional[str]:
    return DEFAULT_MODEL_BY_PROVIDER.get(provider)


def provider_display_name(provider: str) -> str:
    """Human label, falling back to the raw id on a miss."""
    return PROVIDER_DISPLAY_NAMES.get(provider, provider)


def provider_supports_platform_auth(provider: str) -> bool:
    return PROVIDER_SUPPORTS_PLATFORM_AUTH.get(provider) is True


def find_model(model_id: str, provider: Optional[str] = None) -> Optional[CatalogModel]:
    """Look up a model by id (optionally scoped to a provider). None if unknown."""
    providers = (provider,) if provider else MODELS_BY_PROVIDER.keys()
    for prov in providers:
        for model in MODELS_BY_PROVIDER.get(prov, ()):
            if model.id == model_id:
                return model
    return None


def is_known_model(model_id: str, provider: Optional[str] = None) -> bool:
    return find_model(model_id, provider) is not None
