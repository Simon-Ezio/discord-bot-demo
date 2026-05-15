from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"


class ConfigError(ValueError):
    """Raised when environment configuration is missing or invalid."""


@dataclass(frozen=True)
class BotConfig:
    discord_bot_token: str
    minimax_api_key: str
    owner_user_id: str
    owner_username: str
    chat_channel_id: str
    log_channel_id: str
    minimax_base_url: str
    minimax_model: str
    proactive_check_seconds: int
    proactive_min_idle_seconds: int
    proactive_max_idle_seconds: int
    proactive_early_idle_seconds: int
    proactive_backoff_cap_seconds: int
    state_dir: Path
    proxy: str | None
    proxy_ssl_verify: bool

    @classmethod
    def from_env(cls) -> "BotConfig":
        load_dotenv()

        discord_bot_token = _required("DISCORD_BOT_TOKEN")
        minimax_api_key = _required("MINIMAX_API_KEY")
        owner_user_id = _required("OWNER_USER_ID")
        chat_channel_id = _required("CHAT_CHANNEL_ID")
        log_channel_id = _required("LOG_CHANNEL_ID")
        proactive_check_seconds = _positive_int("PROACTIVE_CHECK_SECONDS", "60")
        proactive_min_idle_seconds = _positive_int(
            "PROACTIVE_MIN_IDLE_SECONDS", "300"
        )
        proactive_max_idle_seconds = _positive_int(
            "PROACTIVE_MAX_IDLE_SECONDS", "86400"
        )
        proactive_early_idle_seconds = _positive_int(
            "PROACTIVE_EARLY_IDLE_SECONDS",
            str(max(1, proactive_min_idle_seconds // 2)),
        )
        proactive_backoff_cap_seconds = _positive_int(
            "PROACTIVE_BACKOFF_CAP_SECONDS",
            "7200",
        )

        if proactive_min_idle_seconds > proactive_max_idle_seconds:
            raise ConfigError(
                "PROACTIVE_MIN_IDLE_SECONDS must be less than or equal to "
                "PROACTIVE_MAX_IDLE_SECONDS"
            )

        proxy = _optional("PROXY", "")
        proxy_ssl_verify = _optional("PROXY_SSL_VERIFY", "true").lower() in ("true", "1", "yes")

        return cls(
            discord_bot_token=discord_bot_token,
            minimax_api_key=minimax_api_key,
            owner_user_id=owner_user_id,
            owner_username=_optional("OWNER_USERNAME", "owner"),
            chat_channel_id=chat_channel_id,
            log_channel_id=log_channel_id,
            minimax_base_url=_optional("MINIMAX_BASE_URL", DEFAULT_MINIMAX_BASE_URL),
            minimax_model=_optional("MINIMAX_MODEL", ""),
            proactive_check_seconds=proactive_check_seconds,
            proactive_min_idle_seconds=proactive_min_idle_seconds,
            proactive_max_idle_seconds=proactive_max_idle_seconds,
            proactive_early_idle_seconds=proactive_early_idle_seconds,
            proactive_backoff_cap_seconds=proactive_backoff_cap_seconds,
            state_dir=Path(_optional("STATE_DIR", "state")),
            proxy=proxy or None,
            proxy_ssl_verify=proxy_ssl_verify,
        )


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ConfigError(f"{name} is required")
    return value


def _optional(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value


def _positive_int(name: str, default: str) -> int:
    value = _optional(name, default)
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive integer") from exc

    if parsed <= 0:
        raise ConfigError(f"{name} must be a positive integer")
    return parsed
