from __future__ import annotations

from typing import Any

import httpx


class FishAudioError(RuntimeError):
    pass


class FishAudioClient:
    BASE_URL = "https://api.fish.audio"

    def __init__(self, api_key: str, timeout: float = 45.0) -> None:
        if not api_key.strip():
            raise FishAudioError("Fish Audio API key is required")
        self.api_key = api_key.strip()
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def fetch_voice_models(
        self, page_size: int = 50, page_number: int = 1, self_only: bool = False
    ) -> list[dict[str, str]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.BASE_URL}/model",
                headers=self.headers,
                params={
                    "page_size": max(1, min(page_size, 100)),
                    "page_number": max(1, page_number),
                    "self": str(self_only).lower(),
                },
            )
        if response.is_error:
            raise FishAudioError(
                f"Fish Audio voice fetch failed ({response.status_code}): "
                f"{response.text[:300]}"
            )
        payload: Any = response.json()
        rows: list[Any] = []
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            for key in ("items", "models", "data", "results"):
                if isinstance(payload.get(key), list):
                    rows = payload[key]
                    break

        voices: list[dict[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            voice_id = row.get("_id") or row.get("id") or row.get("model_id")
            if not voice_id:
                continue
            voices.append(
                {
                    "id": str(voice_id),
                    "title": str(row.get("title") or row.get("name") or voice_id),
                }
            )
        return voices

    async def tts(
        self,
        text: str,
        reference_id: str | None = None,
        model: str = "s2.1-pro",
        audio_format: str = "mp3",
    ) -> tuple[bytes, str]:
        body: dict[str, Any] = {"text": text, "format": audio_format}
        if reference_id:
            body["reference_id"] = reference_id
        headers = {
            **self.headers,
            "Content-Type": "application/json",
            "model": model,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.BASE_URL}/v1/tts", headers=headers, json=body
            )
        if response.is_error:
            raise FishAudioError(
                f"Fish Audio TTS failed ({response.status_code}): {response.text[:300]}"
            )
        media_type = response.headers.get("content-type", "audio/mpeg").split(";")[0]
        return response.content, media_type

    async def transcribe(
        self,
        audio: bytes,
        filename: str = "voice.webm",
        content_type: str = "audio/webm",
        model: str = "transcribe-1",
    ) -> dict[str, Any]:
        headers = {**self.headers, "model": model}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.BASE_URL}/v1/asr",
                headers=headers,
                files={"audio": (filename, audio, content_type)},
                data={"ignore_timestamps": "true"},
            )
        if response.is_error:
            raise FishAudioError(
                f"Fish Audio ASR failed ({response.status_code}): {response.text[:300]}"
            )
        payload = response.json()
        text = payload.get("text") or payload.get("transcript") or ""
        return {"text": str(text).strip(), "language": payload.get("language")}
