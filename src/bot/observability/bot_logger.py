from __future__ import annotations

import logging
import re
from typing import Protocol


LOGGER_NAME = "bot.runtime"

SECRET_PATTERNS = (
    re.compile(r"\b(?:DISCORD_BOT_TOKEN|MINIMAX_API_KEY)\s*=\s*\S+", re.IGNORECASE),
    re.compile(r"\b(?:api[_ -]?key|token|secret)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
)


class LogAdapter(Protocol):
    async def send_log(self, text: str) -> None: ...


class BotLogger:
    def __init__(
        self,
        adapter: LogAdapter | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._adapter = adapter
        self._logger = logger or logging.getLogger(LOGGER_NAME)

    async def info(self, message: str) -> None:
        safe_message = self._sanitize(message)
        self._logger.info(safe_message)
        if self._adapter is not None:
            await self._adapter.send_log(safe_message)

    async def error(self, message: str) -> None:
        safe_message = self._sanitize(message)
        self._logger.error(safe_message)
        if self._adapter is not None:
            await self._adapter.send_log(safe_message)

    def _sanitize(self, message: str) -> str:
        safe_message = message
        for pattern in SECRET_PATTERNS:
            safe_message = pattern.sub("[redacted]", safe_message)
        return safe_message
