from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    label: str
    base_url: str
    protocol: str = "openai"


PROVIDERS: dict[str, ProviderPreset] = {
    "openai": ProviderPreset("openai", "OpenAI", "https://api.openai.com"),
    "xai": ProviderPreset("xai", "xAI / Grok", "https://api.x.ai"),
    "openrouter": ProviderPreset("openrouter", "OpenRouter", "https://openrouter.ai/api"),
    "groq": ProviderPreset("groq", "Groq", "https://api.groq.com/openai"),
    "deepseek": ProviderPreset("deepseek", "DeepSeek", "https://api.deepseek.com"),
    "mistral": ProviderPreset("mistral", "Mistral", "https://api.mistral.ai"),
    "anthropic": ProviderPreset("anthropic", "Anthropic", "https://api.anthropic.com", "anthropic"),
    "gemini": ProviderPreset("gemini", "Google Gemini", "https://generativelanguage.googleapis.com", "gemini"),
    "openai-compatible": ProviderPreset("openai-compatible", "OpenAI-compatible", "", "openai"),
}


class AIProviderError(RuntimeError):
    pass


def public_provider_catalog() -> list[dict[str, str]]:
    return [
        {"id": p.id, "label": p.label, "base_url": p.base_url, "protocol": p.protocol}
        for p in PROVIDERS.values()
    ]


def _preset(provider: str, base_url: str | None) -> ProviderPreset:
    provider = provider.strip().lower()
    if provider not in PROVIDERS:
        raise AIProviderError(f"unsupported provider: {provider}")
    p = PROVIDERS[provider]
    if provider == "openai-compatible":
        if not base_url:
            raise AIProviderError("base_url is required for an OpenAI-compatible provider")
        return ProviderPreset(p.id, p.label, base_url.rstrip("/"), p.protocol)
    if base_url:
        return ProviderPreset(p.id, p.label, base_url.rstrip("/"), p.protocol)
    return p


def _ids_from_payload(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            values = []
            for item in data:
                if isinstance(item, dict):
                    value = item.get("id") or item.get("name")
                    if value:
                        values.append(str(value).removeprefix("models/"))
            return sorted(set(values))
        models = payload.get("models")
        if isinstance(models, list):
            values = []
            for item in models:
                if isinstance(item, dict):
                    value = item.get("name") or item.get("id")
                    if value:
                        values.append(str(value).removeprefix("models/"))
            return sorted(set(values))
    return []


class AIProviderClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    async def fetch_models(
        self, provider: str, api_key: str, base_url: str | None = None
    ) -> list[str]:
        p = _preset(provider, base_url)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if p.protocol == "anthropic":
                response = await client.get(
                    f"{p.base_url}/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
            elif p.protocol == "gemini":
                response = await client.get(
                    f"{p.base_url}/v1beta/models",
                    params={"key": api_key},
                )
            else:
                response = await client.get(
                    f"{p.base_url}/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
        if response.is_error:
            raise AIProviderError(
                f"{p.label} model fetch failed ({response.status_code}): "
                f"{response.text[:300]}"
            )
        models = _ids_from_payload(response.json())
        if not models:
            raise AIProviderError(f"{p.label} returned no selectable models")
        return models

    async def chat(
        self,
        provider: str,
        model: str,
        api_key: str,
        messages: list[dict[str, str]],
        base_url: str | None = None,
    ) -> str:
        p = _preset(provider, base_url)
        async with httpx.AsyncClient(timeout=60.0) as client:
            if p.protocol == "anthropic":
                system = "\n".join(
                    m["content"] for m in messages if m.get("role") == "system"
                )
                anth_messages = [
                    {"role": m["role"], "content": m["content"]}
                    for m in messages
                    if m.get("role") in {"user", "assistant"}
                ]
                body: dict[str, Any] = {
                    "model": model,
                    "max_tokens": 1200,
                    "messages": anth_messages,
                }
                if system:
                    body["system"] = system
                response = await client.post(
                    f"{p.base_url}/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=body,
                )
            elif p.protocol == "gemini":
                contents = []
                for m in messages:
                    if m.get("role") == "system":
                        continue
                    role = "model" if m.get("role") == "assistant" else "user"
                    contents.append({"role": role, "parts": [{"text": m["content"]}]})
                response = await client.post(
                    f"{p.base_url}/v1beta/models/{model}:generateContent",
                    params={"key": api_key},
                    json={"contents": contents},
                )
            else:
                response = await client.post(
                    f"{p.base_url}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": model, "messages": messages, "temperature": 0.2},
                )

        if response.is_error:
            raise AIProviderError(
                f"{p.label} chat failed ({response.status_code}): {response.text[:400]}"
            )

        payload = response.json()
        try:
            if p.protocol == "anthropic":
                return "".join(
                    item.get("text", "")
                    for item in payload.get("content", [])
                    if isinstance(item, dict)
                ).strip()
            if p.protocol == "gemini":
                return (
                    payload["candidates"][0]["content"]["parts"][0]["text"].strip()
                )
            return payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(f"unexpected {p.label} response shape") from exc
