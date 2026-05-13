import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from bot.config import DEFAULT_MINIMAX_BASE_URL, BotConfig


ROOT = Path(__file__).resolve().parents[1]
DRY_RUN_TURN_PATH = ROOT / "scripts" / "dry_run_turn.py"
DRY_RUN_SPEC = importlib.util.spec_from_file_location(
    "dry_run_turn", DRY_RUN_TURN_PATH
)
assert DRY_RUN_SPEC is not None
dry_run_turn = importlib.util.module_from_spec(DRY_RUN_SPEC)
assert DRY_RUN_SPEC.loader is not None
DRY_RUN_SPEC.loader.exec_module(dry_run_turn)


def run_script(*args, env=None):
    command_env = os.environ.copy()
    command_env.pop("DISCORD_BOT_TOKEN", None)
    command_env.pop("MINIMAX_API_KEY", None)
    command_env.update(env or {})
    return subprocess.run(
        [sys.executable, *args],
        check=False,
        capture_output=True,
        env=command_env,
        text=True,
    )


def test_show_state_help_exits_zero_and_mentions_state():
    result = run_script("scripts/show_state.py", "--help")

    assert result.returncode == 0
    assert "state" in result.stdout.lower()


def test_dry_run_turn_help_exits_zero_and_mentions_message():
    result = run_script("scripts/dry_run_turn.py", "--help")

    assert result.returncode == 0
    assert "message" in result.stdout.lower()
    assert "--use-minimax" in result.stdout


def test_dry_run_agent_is_default_even_when_minimax_key_exists(tmp_path):
    config = BotConfig(
        discord_bot_token="discord-token",
        minimax_api_key="minimax-key",
        owner_user_id="owner-id",
        owner_username="owner",
        chat_channel_id="chat-id",
        log_channel_id="log-id",
        minimax_base_url=DEFAULT_MINIMAX_BASE_URL,
        minimax_model="MiniMax-Text-01",
        proactive_check_seconds=60,
        proactive_min_idle_seconds=300,
        proactive_max_idle_seconds=900,
        state_dir=Path(tmp_path),
    )

    agent = dry_run_turn.build_agent(config, use_minimax=False)

    assert isinstance(agent, dry_run_turn.DryRunAgent)


def test_show_state_prints_sections_without_secrets(tmp_path):
    result = run_script(
        "scripts/show_state.py",
        "--state-dir",
        str(tmp_path / "state"),
        env={
            "DISCORD_BOT_TOKEN": "discord-secret-token",
            "MINIMAX_API_KEY": "minimax-secret-key",
        },
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout.lower()
    assert "bot identity" in output
    assert "owner profile" in output
    assert "avatar prompt" in output
    assert "relationship journal" in output
    assert "runtime json" in output
    assert "discord-secret-token" not in result.stdout
    assert "minimax-secret-key" not in result.stdout
