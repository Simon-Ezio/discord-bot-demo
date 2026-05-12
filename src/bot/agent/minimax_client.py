from __future__ import annotations

from typing import Any

import httpx


DEFAULT_MINIMAX_MODEL = "MiniMax-Text-01"


class MiniMaxClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "",
        timeout_seconds: float = 30,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._model = model or DEFAULT_MINIMAX_MODEL
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def complete(self, messages: list[dict[str, str]]) -> str:
        payload: dict[str, Any] = {"messages": messages, "model": self._model}

        if self._http_client is not None:
            response = await self._http_client.post(
                self._base_url,
                json=payload,
                headers=self._headers,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            return self._extract_text(response.json())

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as http_client:
            response = await http_client.post(
                self._base_url,
                json=payload,
                headers=self._headers,
            )
            response.raise_for_status()
            return self._extract_text(response.json())

    def _extract_text(self, data: Any) -> str:
        if not isinstance(data, dict):
            raise RuntimeError("MiniMax response did not contain text")

        base_resp = data.get("base_resp")
        if isinstance(base_resp, dict):
            status_code = base_resp.get("status_code")
            if status_code not in (None, 0, "0"):
                status_msg = base_resp.get("status_msg") or "unknown error"
                raise RuntimeError(f"MiniMax API error {status_code}: {status_msg}")

        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content

                text = first_choice.get("text")
                if isinstance(text, str) and text.strip():
                    return text

        for key in ("reply", "output_text", "content"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value

        raise RuntimeError("MiniMax response did not contain text")
