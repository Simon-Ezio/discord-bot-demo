import asyncio
from datetime import datetime, timezone

from bot.models import AgentResult, MemorySnapshot, MessageEvent, RuntimeState
from bot.runtime import BotRuntime


class FakeStore:
    def __init__(self, snapshot: MemorySnapshot):
        self.snapshot = snapshot
        self.saved_runtime_state = None

    def load_snapshot(self) -> MemorySnapshot:
        return self.snapshot

    def save_runtime_state(self, state: RuntimeState) -> None:
        self.saved_runtime_state = state


class FakeCurator:
    def __init__(self):
        self.calls = []

    def apply_updates(self, **updates):
        self.calls.append(updates)


class FakeAgent:
    def __init__(self, result: AgentResult | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls = []

    async def respond(self, snapshot: MemorySnapshot, event: MessageEvent) -> AgentResult:
        self.calls.append((snapshot, event))
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class FakeAdapter:
    def __init__(self):
        self.chat_messages = []

    async def send_chat(self, text: str) -> None:
        self.chat_messages.append(text)


class FakeLogger:
    def __init__(self):
        self.info_messages = []
        self.error_messages = []

    async def info(self, message: str) -> None:
        self.info_messages.append(message)

    async def error(self, message: str) -> None:
        self.error_messages.append(message)


def make_snapshot() -> MemorySnapshot:
    return MemorySnapshot(
        bot_identity="Bot identity",
        owner_profile="Owner profile",
        relationship_journal="Journal",
        avatar_prompt="Avatar",
        runtime_state=RuntimeState(unanswered_proactive_count=2),
    )


def make_event() -> MessageEvent:
    return MessageEvent(
        message_id="msg-1",
        channel_id="chat-1",
        author_id="owner-1",
        author_name="Mina",
        content="My token is secret and the raw prompt is long.",
        created_at=datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc),
        attachments=[],
    )


def test_handle_message_replies_updates_runtime_state_and_logs_safe_summary():
    snapshot = make_snapshot()
    store = FakeStore(snapshot)
    curator = FakeCurator()
    agent = FakeAgent(
        AgentResult(
            reply_text="Hi @everyone, I heard you.",
            bot_identity_updates=["Bot learned something."],
            owner_profile_updates=["Owner shared a detail."],
            relationship_journal_updates=["They talked today."],
            avatar_updates=["Add a green scarf."],
        )
    )
    adapter = FakeAdapter()
    logger = FakeLogger()
    runtime = BotRuntime(store, curator, agent, adapter, logger)
    event = make_event()

    asyncio.run(runtime.handle_message(event))

    assert agent.calls == [(snapshot, event)]
    assert adapter.chat_messages == ["Hi @\u200beveryone, I heard you."]
    assert curator.calls == [
        {
            "bot_identity_updates": ["Bot learned something."],
            "owner_profile_updates": ["Owner shared a detail."],
            "relationship_journal_updates": ["They talked today."],
            "avatar_updates": ["Add a green scarf."],
        }
    ]
    assert snapshot.runtime_state.last_owner_message_at == event.created_at
    assert snapshot.runtime_state.unanswered_proactive_count == 0
    assert store.saved_runtime_state is snapshot.runtime_state
    assert logger.info_messages == [
        "handled owner message message_id=msg-1 channel_id=chat-1 "
        "attachments=0 reply_chars=27 memory_updates=4"
    ]
    assert "secret" not in logger.info_messages[0].lower()
    assert "raw prompt" not in logger.info_messages[0].lower()


def test_handle_message_sends_fallback_and_skips_updates_when_agent_fails():
    snapshot = make_snapshot()
    store = FakeStore(snapshot)
    curator = FakeCurator()
    agent = FakeAgent(error=RuntimeError("MINIMAX_API_KEY=secret"))
    adapter = FakeAdapter()
    logger = FakeLogger()
    runtime = BotRuntime(store, curator, agent, adapter, logger)
    event = make_event()

    asyncio.run(runtime.handle_message(event))

    assert adapter.chat_messages == ["I'm here with you. Tell me a little more?"]
    assert curator.calls == []
    assert store.saved_runtime_state is None
    assert logger.error_messages == [
        "failed handling owner message message_id=msg-1 channel_id=chat-1 "
        "error_type=RuntimeError"
    ]
    assert "secret" not in logger.error_messages[0].lower()
