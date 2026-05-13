from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from bot.models import AttachmentInfo, MessageEvent

try:
    import discord
except ImportError:  # pragma: no cover - exercised only without optional dependency
    discord = None  # type: ignore[assignment]


class DiscordAdapterConfig(Protocol):
    owner_user_id: str
    chat_channel_id: str
    log_channel_id: str


class MessageRuntime(Protocol):
    async def handle_message(self, event: MessageEvent) -> None: ...


def should_accept_message(
    *,
    author_id: str,
    channel_id: str,
    is_bot: bool,
    is_dm: bool,
    config: DiscordAdapterConfig,
) -> bool:
    if is_bot or is_dm:
        return False
    return (
        author_id == config.owner_user_id
        and channel_id == config.chat_channel_id
    )


class DiscordAdapter:
    def __init__(
        self,
        config: DiscordAdapterConfig,
        runtime: MessageRuntime | None = None,
        client: Any | None = None,
        attachment_dir: Path | str | None = None,
    ) -> None:
        if discord is None and client is None:
            raise RuntimeError("discord.py is required to create a DiscordAdapter")

        self.config = config
        self.runtime = runtime
        self.attachment_dir = Path(attachment_dir) if attachment_dir is not None else None
        self.allowed_mentions = self._make_allowed_mentions()
        self.client = client or self._make_client()

    def attach_runtime(self, runtime: MessageRuntime) -> None:
        self.runtime = runtime

    async def on_message(self, message: Any) -> None:
        if self.runtime is None:
            return

        if not should_accept_message(
            author_id=str(message.author.id),
            channel_id=str(message.channel.id),
            is_bot=bool(getattr(message.author, "bot", False)),
            is_dm=self._is_dm(message),
            config=self.config,
        ):
            return

        event = MessageEvent(
            message_id=str(message.id),
            channel_id=str(message.channel.id),
            author_id=str(message.author.id),
            author_name=str(getattr(message.author, "display_name", message.author)),
            content=str(getattr(message, "content", "")),
            created_at=message.created_at,
            attachments=await self.download_image_attachments(message),
        )
        await self.runtime.handle_message(event)

    async def send_chat(self, text: str) -> None:
        channel = await self._resolve_channel(self.config.chat_channel_id)
        await channel.send(text, allowed_mentions=self.allowed_mentions)

    async def send_log(self, text: str) -> None:
        channel = await self._resolve_channel(self.config.log_channel_id)
        await channel.send(text, allowed_mentions=self.allowed_mentions)

    async def download_image_attachments(self, message: Any) -> list[AttachmentInfo]:
        downloaded: list[AttachmentInfo] = []
        for attachment in getattr(message, "attachments", []):
            info = AttachmentInfo(
                filename=str(getattr(attachment, "filename", "")),
                content_type=getattr(attachment, "content_type", None),
                url=getattr(attachment, "url", None),
            )
            if not info.is_image:
                continue

            if self.attachment_dir is None:
                downloaded.append(info)
                continue

            self.attachment_dir.mkdir(parents=True, exist_ok=True)
            local_path = self.attachment_dir / Path(info.filename).name
            await attachment.save(local_path)
            downloaded.append(
                AttachmentInfo(
                    filename=info.filename,
                    content_type=info.content_type,
                    url=info.url,
                    local_path=str(local_path),
                )
            )
        return downloaded

    def _make_allowed_mentions(self) -> Any:
        if discord is None:
            return None
        return discord.AllowedMentions(
            everyone=False,
            roles=False,
            users=True,
            replied_user=True,
        )

    def _make_client(self) -> Any:
        assert discord is not None
        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents, allowed_mentions=self.allowed_mentions)

        @client.event
        async def on_message(message: Any) -> None:
            await self.on_message(message)

        return client

    async def _resolve_channel(self, channel_id: str) -> Any:
        channel = self.client.get_channel(int(channel_id))
        if channel is None:
            channel = await self.client.fetch_channel(int(channel_id))
        return channel

    def _is_dm(self, message: Any) -> bool:
        if discord is not None and isinstance(message.channel, discord.DMChannel):
            return True
        return getattr(message.channel, "guild", None) is None
