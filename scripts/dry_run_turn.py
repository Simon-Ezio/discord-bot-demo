#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bot.config import DEFAULT_MINIMAX_BASE_URL, BotConfig, ConfigError  # noqa: E402
from bot.memory.curator import MemoryCurator  # noqa: E402
from bot.memory.store import MemoryStore  # noqa: E402
from bot.models import AgentResult, MessageEvent  # noqa: E402
from bot.runtime import BotRuntime  # noqa: E402


class ConsoleAdapter:
    async def send_chat(self, text: str) -> None:
        print(f"bot: {text}")


class ConsoleLogger:
    async def info(self, message: str) -> None:
        print(f"info: {message}", file=sys.stderr)

    async def error(self, message: str) -> None:
        print(f"error: {message}", file=sys.stderr)


class DryRunAgent:
    async def respond(self, snapshot, event: MessageEvent) -> AgentResult:
        return AgentResult(
            reply_text=f"Dry run received: {event.content}",
            relationship_journal_updates=[
                f"Dry-run synthetic message at {event.created_at.isoformat()}"
            ],
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one synthetic owner message turn.")
    parser.add_argument("--message", required=True, help="Synthetic owner message text.")
    parser.add_argument(
        "--state-dir",
        default="state",
        help="State directory to initialize and update. Defaults to ./state.",
    )
    parser.add_argument(
        "--use-minimax",
        action="store_true",
        help="Call the real MiniMax API. Defaults to the offline dry-run agent.",
    )
    return parser.parse_args()


def load_dry_run_config(state_dir: Path) -> BotConfig:
    try:
        return replace(BotConfig.from_env(), state_dir=state_dir)
    except ConfigError:
        return BotConfig(
            discord_bot_token=os.getenv("DISCORD_BOT_TOKEN", "dry-run-token"),
            minimax_api_key=os.getenv("MINIMAX_API_KEY", ""),
            owner_user_id=os.getenv("OWNER_USER_ID", "dry-run-owner"),
            owner_username=os.getenv("OWNER_USERNAME", "owner"),
            chat_channel_id=os.getenv("CHAT_CHANNEL_ID", "dry-run-chat"),
            log_channel_id=os.getenv("LOG_CHANNEL_ID", "dry-run-log"),
            minimax_base_url=os.getenv("MINIMAX_BASE_URL", DEFAULT_MINIMAX_BASE_URL),
            minimax_model=os.getenv("MINIMAX_MODEL", ""),
            proactive_check_seconds=int(os.getenv("PROACTIVE_CHECK_SECONDS", "60")),
            proactive_min_idle_seconds=int(
                os.getenv("PROACTIVE_MIN_IDLE_SECONDS", "300")
            ),
            proactive_max_idle_seconds=int(
                os.getenv("PROACTIVE_MAX_IDLE_SECONDS", "86400")
            ),
            proactive_early_idle_seconds=int(
                os.getenv("PROACTIVE_EARLY_IDLE_SECONDS", "150")
            ),
            proactive_backoff_cap_seconds=int(
                os.getenv("PROACTIVE_BACKOFF_CAP_SECONDS", "7200")
            ),
            state_dir=state_dir,
            proxy=None,
            proxy_ssl_verify=True,
        )


def build_agent(config: BotConfig, *, use_minimax: bool):
    if not use_minimax:
        return DryRunAgent()
    if not config.minimax_api_key:
        raise ConfigError("MINIMAX_API_KEY is required with --use-minimax")

    from bot.agent.minimax_client import MiniMaxClient
    from bot.agent.prompt_builder import PromptBuilder
    from bot.agent.relationship_agent import RelationshipAgent

    return RelationshipAgent(
        MiniMaxClient(
            api_key=config.minimax_api_key,
            base_url=config.minimax_base_url,
            model=config.minimax_model,
        ),
        PromptBuilder(config.owner_username),
    )


async def run_turn(message: str, state_dir: Path, *, use_minimax: bool) -> None:
    config = load_dry_run_config(state_dir)
    store = MemoryStore(config.state_dir)
    runtime = BotRuntime(
        store,
        MemoryCurator(store),
        build_agent(config, use_minimax=use_minimax),
        ConsoleAdapter(),
        ConsoleLogger(),
    )
    event = MessageEvent(
        message_id="dry-run-message",
        channel_id=config.chat_channel_id,
        author_id=config.owner_user_id,
        author_name=config.owner_username,
        content=message,
        created_at=datetime.now(UTC),
        attachments=[],
    )
    await runtime.handle_message(event)


def main() -> None:
    args = parse_args()
    asyncio.run(
        run_turn(args.message, Path(args.state_dir), use_minimax=args.use_minimax)
    )


if __name__ == "__main__":
    main()
