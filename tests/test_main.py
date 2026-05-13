import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bot.main import run_proactive_tick
from bot.models import MemorySnapshot, ProactiveDecision, RuntimeState


NOW = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)


class StubStore:
    def __init__(self, snapshot: MemorySnapshot, save_error: Exception | None = None) -> None:
        self.snapshot = snapshot
        self.saved_state = None
        self.save_error = save_error

    def load_snapshot(self) -> MemorySnapshot:
        return self.snapshot

    def save_runtime_state(self, state: RuntimeState) -> None:
        if self.save_error is not None:
            raise self.save_error
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


class SendingAdapter:
    def __init__(self) -> None:
        self.messages = []

    async def send_chat(self, text: str) -> None:
        self.messages.append(text)


class FailingClient:
    def __init__(self) -> None:
        self.closed = False
        self.started = False

    async def start(self, token: str) -> None:
        self.started = True
        raise RuntimeError("connection timeout")

    async def close(self) -> None:
        self.closed = True


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


def test_proactive_tick_logs_state_save_failure_after_successful_send():
    store = StubStore(make_snapshot(), save_error=OSError("disk full"))
    adapter = SendingAdapter()
    logger = StubLogger()

    asyncio.run(
        run_proactive_tick(
            store=store,
            agent=StubAgent(),
            adapter=adapter,
            logger=logger,
            min_idle_seconds=60,
            max_idle_seconds=300,
            now=NOW,
        )
    )

    assert adapter.messages == ["Want to talk?"]
    assert store.saved_state is None
    assert (
        "failed saving proactive runtime state error_type=OSError"
        in logger.errors
    )
    assert "sent proactive message" in logger.infos


def test_proactive_tick_logs_send_and_state_failures_without_raising():
    store = StubStore(make_snapshot(), save_error=OSError("disk full"))
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

    assert store.saved_state is None
    assert logger.errors == [
        "failed saving proactive runtime state error_type=OSError",
        "failed sending proactive message error_type=RuntimeError",
    ]


def test_discord_client_close_is_called_when_start_fails(monkeypatch):
    from bot import main as main_module

    fake_client = FailingClient()

    class FakeAdapter:
        def __init__(self) -> None:
            self.client = fake_client

    def fake_build_runtime(config):
        return FakeAdapter(), object(), object()

    monkeypatch.setattr(main_module, "build_runtime", fake_build_runtime)
    monkeypatch.setattr(
        main_module.BotConfig,
        "from_env",
        classmethod(lambda cls: SimpleNamespace(discord_bot_token="token")),
    )

    try:
        asyncio.run(main_module.amain())
    except SystemExit as exc:
        assert exc.code == 1

    assert fake_client.started is True
    assert fake_client.closed is True
