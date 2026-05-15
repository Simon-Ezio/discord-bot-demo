from __future__ import annotations

from typing import Protocol

from bot.agent.relationship_agent import FALLBACK_REPLY
from bot.models import (
    AgentResult,
    MemorySnapshot,
    MemoryUpdate,
    MessageEvent,
    RuntimeState,
)
from bot.safety import sanitize_discord_output


class SnapshotStore(Protocol):
    def load_snapshot(self) -> MemorySnapshot: ...

    def save_runtime_state(self, state: RuntimeState) -> None: ...

    def save_attachment_metadata(self, filename: str, source_url: str): ...


class MemoryUpdateCurator(Protocol):
    def apply_updates(
        self,
        *,
        bot_identity_updates: list[MemoryUpdate] | None = None,
        owner_profile_updates: list[MemoryUpdate] | None = None,
        relationship_journal_updates: list[MemoryUpdate] | None = None,
        avatar_updates: list[MemoryUpdate] | None = None,
    ) -> None: ...


class ChatAgent(Protocol):
    async def respond(
        self, snapshot: MemorySnapshot, event: MessageEvent
    ) -> AgentResult: ...


class ChatAdapter(Protocol):
    async def send_chat(self, text: str) -> None: ...


class RuntimeLogger(Protocol):
    async def info(self, message: str) -> None: ...

    async def error(self, message: str) -> None: ...


class BotRuntime:
    def __init__(
        self,
        store: SnapshotStore,
        curator: MemoryUpdateCurator,
        agent: ChatAgent,
        adapter: ChatAdapter,
        logger: RuntimeLogger,
    ) -> None:
        self._store = store
        self._curator = curator
        self._agent = agent
        self._adapter = adapter
        self._logger = logger

    async def handle_message(self, event: MessageEvent) -> None:
        snapshot = self._store.load_snapshot()

        try:
            result = await self._agent.respond(snapshot, event)
        except Exception as exc:
            await self._safe_send_chat(FALLBACK_REPLY, event)
            await self._logger.error(
                "failed handling owner message "
                f"message_id={event.message_id} "
                f"channel_id={event.channel_id} "
                f"error_type={type(exc).__name__}"
            )
            return

        reply_text = sanitize_discord_output(result.reply_text)
        if not await self._safe_send_chat(reply_text, event):
            return

        avatar_updates = [
            *result.avatar_updates,
            *self._persist_attachment_references(event),
        ]

        runtime_state = snapshot.runtime_state
        runtime_state.last_owner_message_at = event.created_at
        runtime_state.unanswered_proactive_count = 0
        try:
            self._store.save_runtime_state(runtime_state)
        except Exception as exc:
            await self._logger.error(
                "failed saving runtime state "
                f"message_id={event.message_id} "
                f"error_type={type(exc).__name__}"
            )

        try:
            self._curator.apply_updates(
                bot_identity_updates=result.bot_identity_updates,
                owner_profile_updates=result.owner_profile_updates,
                relationship_journal_updates=result.relationship_journal_updates,
                avatar_updates=avatar_updates,
            )
        except Exception as exc:
            await self._logger.error(
                "failed applying memory updates "
                f"message_id={event.message_id} "
                f"error_type={type(exc).__name__}"
            )

        memory_update_count = (
            len(result.bot_identity_updates)
            + len(result.owner_profile_updates)
            + len(result.relationship_journal_updates)
            + len(avatar_updates)
        )
        await self._logger.info(
            "handled owner message "
            f"message_id={event.message_id} "
            f"channel_id={event.channel_id} "
            f"attachments={len(event.attachments)} "
            f"reply_chars={len(reply_text)} "
            f"memory_updates={memory_update_count}"
        )

    async def _safe_send_chat(self, text: str, event: MessageEvent) -> bool:
        try:
            await self._adapter.send_chat(text)
        except Exception as exc:
            await self._logger.error(
                "failed sending chat message "
                f"message_id={event.message_id} "
                f"channel_id={event.channel_id} "
                f"error_type={type(exc).__name__}"
            )
            return False
        return True

    def _persist_attachment_references(self, event: MessageEvent) -> list[MemoryUpdate]:
        updates: list[MemoryUpdate] = []
        for attachment in event.attachments:
            if not attachment.is_image:
                continue
            source = attachment.local_path or attachment.url
            if not source:
                continue
            try:
                metadata_path = self._store.save_attachment_metadata(
                    attachment.filename,
                    source,
                )
            except Exception:
                continue
            updates.append(
                MemoryUpdate(
                    value=(
                        "Image attachment available for avatar consideration: "
                        f"filename={attachment.filename}; source={source}; "
                        f"metadata={metadata_path}"
                    )
                )
            )
        return updates
