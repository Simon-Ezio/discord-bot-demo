import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from bot.platforms.discord_adapter import DiscordAdapter, should_accept_message


@dataclass(frozen=True)
class FilterConfig:
    owner_user_id: str = "owner-1"
    chat_channel_id: str = "chat-1"
    log_channel_id: str = "log-1"


@dataclass(frozen=True)
class NumericChannelConfig:
    owner_user_id: str = "owner-1"
    chat_channel_id: str = "1001"
    log_channel_id: str = "1002"


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, text, *, allowed_mentions=None):
        self.sent.append((text, allowed_mentions))


class FakeClient:
    def __init__(self, channels):
        self.channels = channels

    def get_channel(self, channel_id):
        return self.channels.get(str(channel_id))


class FakeRuntime:
    def __init__(self):
        self.events = []

    async def handle_message(self, event):
        self.events.append(event)


class FakeAttachment:
    def __init__(
        self,
        *,
        filename,
        attachment_id=None,
        content_type="image/png",
        url="https://cdn.example/image.png",
    ):
        self.filename = filename
        self.id = attachment_id
        self.content_type = content_type
        self.url = url
        self.saved_paths = []

    async def save(self, path):
        self.saved_paths.append(Path(path))
        Path(path).write_bytes(b"image")


def make_message(**overrides):
    data = {
        "id": "message-1",
        "channel": SimpleNamespace(id="chat-1", guild=object()),
        "author": SimpleNamespace(id="owner-1", bot=False, display_name="Mina"),
        "content": "hello",
        "created_at": datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc),
        "attachments": [],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_should_accept_message_accepts_owner_in_chat_channel():
    assert should_accept_message(
        author_id="owner-1",
        channel_id="chat-1",
        is_bot=False,
        is_dm=False,
        config=FilterConfig(),
    )


def test_should_accept_message_rejects_non_owner():
    assert not should_accept_message(
        author_id="other-1",
        channel_id="chat-1",
        is_bot=False,
        is_dm=False,
        config=FilterConfig(),
    )


def test_should_accept_message_rejects_wrong_channel():
    assert not should_accept_message(
        author_id="owner-1",
        channel_id="other-channel",
        is_bot=False,
        is_dm=False,
        config=FilterConfig(),
    )


def test_should_accept_message_rejects_bot_author():
    assert not should_accept_message(
        author_id="owner-1",
        channel_id="chat-1",
        is_bot=True,
        is_dm=False,
        config=FilterConfig(),
    )


def test_should_accept_message_rejects_dm():
    assert not should_accept_message(
        author_id="owner-1",
        channel_id="chat-1",
        is_bot=False,
        is_dm=True,
        config=FilterConfig(),
    )


def test_send_chat_uses_fallback_for_blank_messages():
    chat_channel = FakeChannel()
    adapter = DiscordAdapter(
        NumericChannelConfig(),
        client=FakeClient({"1001": chat_channel}),
    )

    asyncio.run(adapter.send_chat(" \n\t "))

    assert [text for text, _ in chat_channel.sent] == [
        "I'm here, but I lost the thread for a second."
    ]


def test_send_chat_chunks_long_messages_under_discord_limit():
    chat_channel = FakeChannel()
    adapter = DiscordAdapter(
        NumericChannelConfig(),
        client=FakeClient({"1001": chat_channel}),
    )

    asyncio.run(adapter.send_chat("x" * 3900))

    sent_texts = [text for text, _ in chat_channel.sent]
    assert "".join(sent_texts) == "x" * 3900
    assert [len(text) for text in sent_texts] == [1900, 1900, 100]


def test_send_log_skips_blank_messages_and_chunks_long_messages():
    log_channel = FakeChannel()
    adapter = DiscordAdapter(
        NumericChannelConfig(),
        client=FakeClient({"1002": log_channel}),
    )

    asyncio.run(adapter.send_log("   "))
    asyncio.run(adapter.send_log("y" * 2001))

    sent_texts = [text for text, _ in log_channel.sent]
    assert sent_texts == ["y" * 1900, "y" * 101]


def test_on_message_converts_accepted_message_and_filters_others():
    runtime = FakeRuntime()
    adapter = DiscordAdapter(
        FilterConfig(),
        runtime=runtime,
        client=FakeClient({}),
    )
    accepted = make_message()
    rejected = make_message(author=SimpleNamespace(id="other-1", bot=False))

    asyncio.run(adapter.on_message(accepted))
    asyncio.run(adapter.on_message(rejected))

    assert len(runtime.events) == 1
    event = runtime.events[0]
    assert event.message_id == "message-1"
    assert event.channel_id == "chat-1"
    assert event.author_id == "owner-1"
    assert event.author_name == "Mina"
    assert event.content == "hello"
    assert event.created_at == accepted.created_at


def test_download_image_attachments_uses_unique_safe_paths(tmp_path):
    attachments = [
        FakeAttachment(filename="../avatar.png", attachment_id="att-1"),
        FakeAttachment(filename="../avatar.png", attachment_id="att-2"),
    ]
    adapter = DiscordAdapter(
        FilterConfig(),
        client=FakeClient({}),
        attachment_dir=tmp_path,
    )

    downloaded = asyncio.run(
        adapter.download_image_attachments(
            make_message(id="message/1", attachments=attachments)
        )
    )

    local_paths = [Path(info.local_path) for info in downloaded]
    assert len(set(local_paths)) == 2
    assert all(path.parent == tmp_path for path in local_paths)
    assert all(path.name.endswith("avatar.png") for path in local_paths)
    assert attachments[0].saved_paths != attachments[1].saved_paths


def test_allowed_mentions_denies_users_and_replied_user_when_discord_available():
    adapter = DiscordAdapter(FilterConfig(), client=FakeClient({}))

    allowed_mentions = adapter.allowed_mentions

    if allowed_mentions is not None:
        assert allowed_mentions.everyone is False
        assert allowed_mentions.roles is False
        assert allowed_mentions.users is False
        assert allowed_mentions.replied_user is False
