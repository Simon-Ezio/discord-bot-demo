import asyncio
from datetime import datetime, timedelta, timezone

from bot.main import run_proactive_tick
from bot.models import MemorySnapshot, ProactiveDecision, RuntimeState


NOW = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)


class StubStore:
    def __init__(self, snapshot: MemorySnapshot) -> None:
        self.snapshot = snapshot
        self.saved_state = None

    def load_snapshot(self) -> MemorySnapshot:
        return self.snapshot

    def save_runtime_state(self, state: RuntimeState) -> None:
        self.saved_state = state


class StubAgent:
    async def plan_proactive(self, snapshot: MemorySnapshot) -> ProactiveDecision:
        return ProactiveDecision(
            should_send=True,
            reason="Owner has been quiet.",
            message="Want to talk?",
        )


class FailingAdapter:
    async def send_chat(self, text: str) -> None:
        raise RuntimeError("discord unavailable")


class StubLogger:
    def __init__(self) -> None:
        self.errors = []
        self.infos = []

    async def error(self, message: str) -> None:
        self.errors.append(message)

    async def info(self, message: str) -> None:
        self.infos.append(message)


def make_snapshot() -> MemorySnapshot:
    return MemorySnapshot(
        bot_identity="Bot identity",
        owner_profile="Owner profile",
        relationship_journal="Relationship journal",
        avatar_prompt="Avatar prompt",
        runtime_state=RuntimeState(
            last_owner_message_at=NOW - timedelta(seconds=120),
        ),
    )


def test_proactive_tick_records_send_failure_for_backoff():
    store = StubStore(make_snapshot())
    logger = StubLogger()

    asyncio.run(
        run_proactive_tick(
            store=store,
            agent=StubAgent(),
            adapter=FailingAdapter(),
            logger=logger,
            min_idle_seconds=60,
            max_idle_seconds=300,
            now=NOW,
        )
    )

    assert store.saved_state is store.snapshot.runtime_state
    assert store.saved_state.last_proactive_sent_at == NOW
    assert (
        store.saved_state.last_proactive_reason
        == "send_failed: Owner has been quiet."
    )
    assert store.saved_state.last_proactive_message == "Want to talk?"
    assert store.saved_state.unanswered_proactive_count == 1
    assert logger.errors
