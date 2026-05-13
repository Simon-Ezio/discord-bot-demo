import os
import subprocess
import sys


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
