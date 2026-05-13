import asyncio
from datetime import datetime, timezone

from bot.models import AgentResult, AttachmentInfo, MemorySnapshot, MessageEvent, RuntimeState
from bot.observability.bot_logger import BotLogger
from bot.runtime import BotRuntime


class FakeStore:
    def __init__(self, snapshot: MemorySnapshot):
        self.snapshot = snapshot
        self.saved_runtime_state = None
        self.attachment_metadata = []

    def load_snapshot(self) -> MemorySnapshot:
        return self.snapshot

    def save_runtime_state(self, state: RuntimeState) -> None:
        self.saved_runtime_state = state

    def save_attachment_metadata(self, filename: str, source_url: str):
        self.attachment_metadata.append((filename, source_url))
        return f"state/attachments/{filename}.json"


class FailingStore(FakeStore):
    def save_runtime_state(self, state: RuntimeState) -> None:
        raise OSError("disk full")


class FakeCurator:
    def __init__(self):
        self.calls = []

    def apply_updates(self, **updates):
        self.calls.append(updates)


class FailingCurator(FakeCurator):
    def apply_updates(self, **updates):
        raise OSError("memory write failed")


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
    def __init__(self, error: Exception | None = None):
        self.chat_messages = []
        self.error = error

    async def send_chat(self, text: str) -> None:
        if self.error is not None:
            raise self.error
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


def make_event_with_image_attachment() -> MessageEvent:
    return MessageEvent(
        message_id="msg-2",
        channel_id="chat-1",
        author_id="owner-1",
        author_name="Mina",
        content="Maybe this is your avatar.",
        created_at=datetime(2026, 5, 13, 12, 5, tzinfo=timezone.utc),
        attachments=[
            AttachmentInfo(
                filename="avatar.png",
                content_type="image/png",
                url="https://cdn.example/avatar.png",
                local_path="state/attachments/msg-2-avatar.png",
            )
        ],
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


def test_handle_message_logs_send_failure_and_skips_memory_updates():
    snapshot = make_snapshot()
    store = FakeStore(snapshot)
    curator = FakeCurator()
    agent = FakeAgent(AgentResult(reply_text="hello"))
    adapter = FakeAdapter(error=RuntimeError("discord down"))
    logger = FakeLogger()
    runtime = BotRuntime(store, curator, agent, adapter, logger)

    asyncio.run(runtime.handle_message(make_event()))

    assert curator.calls == []
    assert store.saved_runtime_state is None
    assert logger.error_messages == [
        "failed sending chat message message_id=msg-1 channel_id=chat-1 "
        "error_type=RuntimeError"
    ]


def test_handle_message_logs_persistence_failures_after_reply():
    snapshot = make_snapshot()
    store = FailingStore(snapshot)
    curator = FailingCurator()
    agent = FakeAgent(AgentResult(reply_text="hello"))
    adapter = FakeAdapter()
    logger = FakeLogger()
    runtime = BotRuntime(store, curator, agent, adapter, logger)

    asyncio.run(runtime.handle_message(make_event()))

    assert adapter.chat_messages == ["hello"]
    assert snapshot.runtime_state.last_owner_message_at == make_event().created_at
    assert snapshot.runtime_state.unanswered_proactive_count == 0
    assert logger.error_messages == [
        "failed saving runtime state message_id=msg-1 error_type=OSError",
        "failed applying memory updates message_id=msg-1 error_type=OSError",
    ]


def test_handle_message_persists_image_attachment_references_to_avatar_updates():
    snapshot = make_snapshot()
    store = FakeStore(snapshot)
    curator = FakeCurator()
    agent = FakeAgent(AgentResult(reply_text="hello"))
    adapter = FakeAdapter()
    logger = FakeLogger()
    runtime = BotRuntime(store, curator, agent, adapter, logger)

    asyncio.run(runtime.handle_message(make_event_with_image_attachment()))

    assert store.attachment_metadata == [
        ("avatar.png", "state/attachments/msg-2-avatar.png")
    ]
    avatar_updates = curator.calls[0]["avatar_updates"]
    assert len(avatar_updates) == 1
    assert "avatar.png" in avatar_updates[0]
    assert "state/attachments/msg-2-avatar.png" in avatar_updates[0]


class FailingLogAdapter:
    async def send_log(self, text: str) -> None:
        raise RuntimeError("discord unavailable")


class CapturingStdlibLogger:
    def __init__(self):
        self.info_messages = []
        self.error_messages = []
        self.exception_messages = []

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def error(self, message: str) -> None:
        self.error_messages.append(message)

    def exception(self, message: str) -> None:
        self.exception_messages.append(message)


def test_bot_logger_keeps_stdlib_logging_best_effort_when_adapter_fails():
    stdlib_logger = CapturingStdlibLogger()
    logger = BotLogger(adapter=FailingLogAdapter(), logger=stdlib_logger)

    asyncio.run(logger.info("token=secret-value"))
    asyncio.run(logger.error("MINIMAX_API_KEY=secret-value"))

    assert stdlib_logger.info_messages == ["[redacted]"]
    assert stdlib_logger.error_messages == ["[redacted]"]
    assert stdlib_logger.exception_messages == [
        "failed sending bot info log to adapter",
        "failed sending bot error log to adapter",
    ]
