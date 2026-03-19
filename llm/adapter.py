"""LLM adapter — single interface for OpenAI-compatible and Anthropic providers."""

import requests
from llm.config import load_config

ANTHROPIC_VERSION = "2023-06-01"


def complete(messages: list[dict], system_prompt: str | None = None) -> str:
    """
    Send a chat completion request to the configured LLM provider.

    Args:
        messages: List of {"role": str, "content": str} dicts.
        system_prompt: Optional system prompt string.

    Returns:
        The model's text response.

    Raises:
        RuntimeError: On API errors or empty responses.
    """
    cfg = load_config()["llm"]

    if cfg["provider_type"] == "anthropic":
        return _anthropic(cfg, messages, system_prompt)
    return _openai(cfg, messages, system_prompt)


def _openai(cfg: dict, messages: list[dict], system_prompt: str | None) -> str:
    payload = {
        "model": cfg["model"],
        "messages": [
            *(
                [{"role": "system", "content": system_prompt}]
                if system_prompt
                else []
            ),
            *messages,
        ],
    }

    response = requests.post(
        f"{cfg['base_url']}/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
        json=payload,
        timeout=120,
    )

    data = response.json()

    if not response.ok or "error" in data:
        err = data.get("error", {})
        raise RuntimeError(
            f"OpenAI API error ({response.status_code}): {err.get('message', data)}"
        )

    content = data.get("choices", [{}])[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError("OpenAI: empty response from model")
    return content


def _anthropic(cfg: dict, messages: list[dict], system_prompt: str | None) -> str:
    payload = {
        "model": cfg["model"],
        "max_tokens": 1024,
        "messages": messages,
        **({"system": system_prompt} if system_prompt else {}),
    }

    response = requests.post(
        f"{cfg['base_url']}/v1/messages",
        headers={
            "Content-Type": "application/json",
            "x-api-key": cfg["api_key"],
            "anthropic-version": ANTHROPIC_VERSION,
        },
        json=payload,
        timeout=120,
    )

    data = response.json()

    if not response.ok or "error" in data:
        err = data.get("error", {})
        raise RuntimeError(
            f"Anthropic API error ({response.status_code}): {err.get('message', data)}"
        )

    blocks = data.get("content", [])
    text_block = next((b for b in blocks if b.get("type") == "text"), None)
    if not text_block:
        raise RuntimeError("Anthropic: empty response from model")
    return text_block["text"]
