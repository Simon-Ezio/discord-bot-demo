from dataclasses import dataclass

from bot.platforms.discord_adapter import should_accept_message


@dataclass(frozen=True)
class FilterConfig:
    owner_user_id: str = "owner-1"
    chat_channel_id: str = "chat-1"


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
