from __future__ import annotations

from pathlib import Path
import re
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
    proxy: str | None
    proxy_ssl_verify: bool


class MessageRuntime(Protocol):
    async def handle_message(self, event: MessageEvent) -> None: ...


CHAT_EMPTY_FALLBACK = "I'm here, but I lost the thread for a second."
DISCORD_MESSAGE_CHUNK_SIZE = 1900
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


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
        for chunk in _chunk_discord_message(text, fallback=CHAT_EMPTY_FALLBACK):
            await channel.send(chunk, allowed_mentions=self.allowed_mentions)

    async def send_log(self, text: str) -> None:
        chunks = _chunk_discord_message(text, fallback=None)
        if not chunks:
            return

        channel = await self._resolve_channel(self.config.log_channel_id)
        for chunk in chunks:
            await channel.send(chunk, allowed_mentions=self.allowed_mentions)

    async def download_image_attachments(self, message: Any) -> list[AttachmentInfo]:
        downloaded: list[AttachmentInfo] = []
        for index, attachment in enumerate(getattr(message, "attachments", []), start=1):
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
            local_path = self.attachment_dir / _safe_attachment_filename(
                message=message,
                attachment=attachment,
                filename=info.filename,
                index=index,
            )
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
            users=False,
            replied_user=False,
        )

    def _make_client(self) -> Any:
        assert discord is not None
        import ssl

        import aiohttp

        intents = discord.Intents.default()
        intents.message_content = True
        client_kwargs: dict[str, Any] = {
            "intents": intents,
            "allowed_mentions": self.allowed_mentions,
        }
        if self.config.proxy:
            client_kwargs["proxy"] = self.config.proxy
        if self.config.proxy and not self.config.proxy_ssl_verify:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            client_kwargs["connector"] = aiohttp.TCPConnector(limit=0, ssl=ssl_ctx)
        client = discord.Client(**client_kwargs)

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


def _chunk_discord_message(text: str, *, fallback: str | None) -> list[str]:
    normalized = text.strip()
    if not normalized:
        if fallback is None:
            return []
        normalized = fallback

    return [
        normalized[start : start + DISCORD_MESSAGE_CHUNK_SIZE]
        for start in range(0, len(normalized), DISCORD_MESSAGE_CHUNK_SIZE)
    ]


def _safe_attachment_filename(
    *,
    message: Any,
    attachment: Any,
    filename: str,
    index: int,
) -> str:
    original_name = Path(filename).name or "attachment"
    safe_name = SAFE_FILENAME_RE.sub("_", original_name).strip("._") or "attachment"
    message_id = _safe_identifier(getattr(message, "id", "message"))
    attachment_id = _safe_identifier(getattr(attachment, "id", index))
    return f"{message_id}-{attachment_id}-{index}-{safe_name}"


def _safe_identifier(value: object) -> str:
    safe_value = SAFE_FILENAME_RE.sub("_", str(value)).strip("._")
    return safe_value or "unknown"
