"""Ruflo → Kimi model mapping.

Per the Ruflo-Kimi Bridge spec:
| Ruflo Model | Kimi Model             |
|-------------|------------------------|
| haiku       | moonshot-v1-8k         |
| sonnet      | moonshot-v1-32k        |
| opus        | moonshot-v1-128k       |
| inherit     | moonshot-v1-32k        |

You can also pass explicit Kimi model names directly.
"""

from __future__ import annotations

# Ruflo alias → Kimi model name
# sonnet and opus route to the flagship kimi-k2.6 model
RUFLO_TO_KIMI: dict[str, str] = {
    "haiku": "moonshot-v1-8k",
    "sonnet": "kimi-k2.6",
    "opus": "kimi-k2.6",
    "inherit": "kimi-k2.6",
}

# Kimi model name → context window size (tokens)
KIMI_CONTEXT_SIZES: dict[str, int] = {
    "moonshot-v1-8k": 8192,
    "moonshot-v1-32k": 32768,
    "moonshot-v1-128k": 128000,
    "kimi-k2-0712-preview": 128000,
    "kimi-k2.6": 256000,
}


def resolve_kimi_model(model: str) -> str:
    """Return the actual Kimi model name for a given Ruflo alias or Kimi model name."""
    # If it's already a known Kimi model, return as-is
    if model in KIMI_CONTEXT_SIZES:
        return model
    # If it's a Ruflo alias, map it
    if model in RUFLO_TO_KIMI:
        return RUFLO_TO_KIMI[model]
    # Unknown — pass through (bridge may still accept it)
    return model


def get_context_size(model: str) -> int:
    """Get context window size for a model (Ruflo alias or Kimi name)."""
    kimi_name = resolve_kimi_model(model)
    return KIMI_CONTEXT_SIZES.get(kimi_name, 32768)


def list_model_mappings() -> dict[str, dict[str, str | int]]:
    """Return all known mappings as a dict."""
    result: dict[str, dict[str, str | int]] = {}
    for ruflo, kimi in RUFLO_TO_KIMI.items():
        result[ruflo] = {
            "kimi_model": kimi,
            "context_tokens": KIMI_CONTEXT_SIZES.get(kimi, 32768),
        }
    for kimi, size in KIMI_CONTEXT_SIZES.items():
        if kimi not in result:
            result[kimi] = {
                "kimi_model": kimi,
                "context_tokens": size,
            }
    return result
