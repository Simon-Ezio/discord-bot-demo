from __future__ import annotations

from typing import Any

import httpx


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
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def complete(self, messages: list[dict[str, str]]) -> str:
        payload: dict[str, Any] = {"messages": messages}
        if self._model:
            payload["model"] = self._model

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
            return ""

        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content

                text = first_choice.get("text")
                if isinstance(text, str):
                    return text

        for key in ("reply", "output_text", "content"):
            value = data.get(key)
            if isinstance(value, str):
                return value

        return ""
