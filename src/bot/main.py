from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from bot.agent.minimax_client import MiniMaxClient
from bot.agent.prompt_builder import PromptBuilder
from bot.agent.relationship_agent import RelationshipAgent
from bot.config import BotConfig
from bot.memory.curator import MemoryCurator
from bot.memory.store import MemoryStore
from bot.observability.bot_logger import BotLogger
from bot.platforms.discord_adapter import DiscordAdapter
from bot.runtime import BotRuntime
from bot.scheduler.proactive import (
    ProactivePlanner,
    ProactivePolicy,
    apply_proactive_sent,
)


async def run_proactive_loop(
    *,
    config: BotConfig,
    store: MemoryStore,
    agent: RelationshipAgent,
    adapter: DiscordAdapter,
    logger: BotLogger,
) -> None:
    policy = ProactivePolicy(
        min_idle_seconds=config.proactive_min_idle_seconds,
        max_idle_seconds=config.proactive_max_idle_seconds,
    )
    planner = ProactivePlanner(policy, agent)

    while True:
        await asyncio.sleep(config.proactive_check_seconds)
        now = datetime.now(UTC)
        snapshot = store.load_snapshot()

        try:
            decision = await planner.maybe_plan(snapshot, now)
        except Exception as exc:
            await logger.error(
                "failed planning proactive message "
                f"error_type={type(exc).__name__}"
            )
            continue

        if not decision.should_send:
            if decision.skip_reason:
                await logger.info(f"skipped proactive message reason={decision.skip_reason}")
            continue

        try:
            await adapter.send_chat(decision.message)
            store.save_runtime_state(
                apply_proactive_sent(snapshot.runtime_state, decision, now)
            )
            await logger.info("sent proactive message")
        except Exception as exc:
            await logger.error(
                "failed sending proactive message "
                f"error_type={type(exc).__name__}"
            )


def build_runtime(config: BotConfig) -> tuple[DiscordAdapter, BotRuntime, BotLogger]:
    store = MemoryStore(config.state_dir)
    curator = MemoryCurator(store)
    client = MiniMaxClient(
        api_key=config.minimax_api_key,
        base_url=config.minimax_base_url,
        model=config.minimax_model,
    )
    prompt_builder = PromptBuilder(config.owner_username)
    agent = RelationshipAgent(client, prompt_builder)
    adapter = DiscordAdapter(
        config,
        attachment_dir=store.attachments_dir,
    )
    logger = BotLogger(adapter)
    runtime = BotRuntime(store, curator, agent, adapter, logger)
    adapter.attach_runtime(runtime)

    proactive_task: asyncio.Task[None] | None = None

    @adapter.client.event
    async def on_ready() -> None:
        nonlocal proactive_task
        await logger.info("discord client ready")
        if proactive_task is None or proactive_task.done():
            proactive_task = asyncio.create_task(
                run_proactive_loop(
                    config=config,
                    store=store,
                    agent=agent,
                    adapter=adapter,
                    logger=logger,
                )
            )

    return adapter, runtime, logger


async def amain() -> None:
    logging.basicConfig(level=logging.INFO)
    config = BotConfig.from_env()
    adapter, _runtime, _logger = build_runtime(config)
    await adapter.client.start(config.discord_bot_token)


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
