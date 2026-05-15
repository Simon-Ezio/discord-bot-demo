from pathlib import Path

import pytest

import bot.config as config_module
from bot.config import BotConfig, ConfigError


CONFIG_ENV_VARS = (
    "DISCORD_BOT_TOKEN",
    "MINIMAX_API_KEY",
    "OWNER_USER_ID",
    "OWNER_USERNAME",
    "CHAT_CHANNEL_ID",
    "LOG_CHANNEL_ID",
    "MINIMAX_BASE_URL",
    "MINIMAX_MODEL",
    "PROACTIVE_CHECK_SECONDS",
    "PROACTIVE_MIN_IDLE_SECONDS",
    "PROACTIVE_MAX_IDLE_SECONDS",
    "PROACTIVE_EARLY_IDLE_SECONDS",
    "PROACTIVE_BACKOFF_CAP_SECONDS",
    "STATE_DIR",
)


@pytest.fixture(autouse=True)
def isolate_config_env(monkeypatch):
    for name in CONFIG_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config_module, "load_dotenv", lambda: False)


def test_from_env_parses_required_and_optional_values(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-token")
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("OWNER_USER_ID", "123456")
    monkeypatch.setenv("OWNER_USERNAME", "cm6550")
    monkeypatch.setenv("CHAT_CHANNEL_ID", "987654")
    monkeypatch.setenv("LOG_CHANNEL_ID", "456789")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://example.com/chat")
    monkeypatch.setenv("MINIMAX_MODEL", "abab6.5-chat")
    monkeypatch.setenv("PROACTIVE_CHECK_SECONDS", "30")
    monkeypatch.setenv("PROACTIVE_MIN_IDLE_SECONDS", "120")
    monkeypatch.setenv("PROACTIVE_MAX_IDLE_SECONDS", "240")
    monkeypatch.setenv("PROACTIVE_EARLY_IDLE_SECONDS", "45")
    monkeypatch.setenv("PROACTIVE_BACKOFF_CAP_SECONDS", "90")
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "custom-state"))

    config = BotConfig.from_env()

    assert config.discord_bot_token == "discord-token"
    assert config.minimax_api_key == "minimax-key"
    assert config.owner_user_id == "123456"
    assert config.owner_username == "cm6550"
    assert config.chat_channel_id == "987654"
    assert config.log_channel_id == "456789"
    assert config.minimax_base_url == "https://example.com/chat"
    assert config.minimax_model == "abab6.5-chat"
    assert config.proactive_check_seconds == 30
    assert config.proactive_min_idle_seconds == 120
    assert config.proactive_max_idle_seconds == 240
    assert config.proactive_early_idle_seconds == 45
    assert config.proactive_backoff_cap_seconds == 90
    assert config.state_dir == tmp_path / "custom-state"


def test_from_env_requires_core_values(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("OWNER_USER_ID", "123456")
    monkeypatch.setenv("CHAT_CHANNEL_ID", "987654")
    monkeypatch.setenv("LOG_CHANNEL_ID", "456789")

    with pytest.raises(ConfigError, match="DISCORD_BOT_TOKEN"):
        BotConfig.from_env()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PROACTIVE_CHECK_SECONDS", "0"),
        ("PROACTIVE_MIN_IDLE_SECONDS", "-1"),
        ("PROACTIVE_MAX_IDLE_SECONDS", "not-an-int"),
        ("PROACTIVE_EARLY_IDLE_SECONDS", "0"),
        ("PROACTIVE_BACKOFF_CAP_SECONDS", "-1"),
    ],
)
def test_from_env_rejects_non_positive_or_non_integer_proactive_values(
    monkeypatch, name, value
):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-token")
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("OWNER_USER_ID", "123456")
    monkeypatch.setenv("CHAT_CHANNEL_ID", "987654")
    monkeypatch.setenv("LOG_CHANNEL_ID", "456789")
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigError, match=name):
        BotConfig.from_env()


def test_from_env_rejects_min_idle_greater_than_max_idle(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-token")
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("OWNER_USER_ID", "123456")
    monkeypatch.setenv("CHAT_CHANNEL_ID", "987654")
    monkeypatch.setenv("LOG_CHANNEL_ID", "456789")
    monkeypatch.setenv("PROACTIVE_MIN_IDLE_SECONDS", "901")
    monkeypatch.setenv("PROACTIVE_MAX_IDLE_SECONDS", "900")

    with pytest.raises(ConfigError, match="PROACTIVE_MIN_IDLE_SECONDS"):
        BotConfig.from_env()


def test_from_env_uses_defaults(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-token")
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("OWNER_USER_ID", "123456")
    monkeypatch.delenv("OWNER_USERNAME", raising=False)
    monkeypatch.setenv("CHAT_CHANNEL_ID", "987654")
    monkeypatch.setenv("LOG_CHANNEL_ID", "456789")
    monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
    monkeypatch.delenv("PROACTIVE_CHECK_SECONDS", raising=False)
    monkeypatch.delenv("PROACTIVE_MIN_IDLE_SECONDS", raising=False)
    monkeypatch.delenv("PROACTIVE_MAX_IDLE_SECONDS", raising=False)
    monkeypatch.delenv("PROACTIVE_EARLY_IDLE_SECONDS", raising=False)
    monkeypatch.delenv("PROACTIVE_BACKOFF_CAP_SECONDS", raising=False)
    monkeypatch.delenv("STATE_DIR", raising=False)

    config = BotConfig.from_env()

    assert config.owner_username == "owner"
    assert (
        config.minimax_base_url
        == "https://api.minimax.chat/v1/text/chatcompletion_v2"
    )
    assert config.proactive_check_seconds == 60
    assert config.proactive_min_idle_seconds == 300
    assert config.proactive_max_idle_seconds == 86400
    assert config.proactive_early_idle_seconds == 150
    assert config.proactive_backoff_cap_seconds == 7200
    assert config.state_dir == Path("state")
