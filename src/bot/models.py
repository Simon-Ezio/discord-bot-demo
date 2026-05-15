from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


RASTER_IMAGE_CONTENT_TYPES = {
    "image/apng",
    "image/avif",
    "image/bmp",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}

RASTER_IMAGE_EXTENSIONS = {
    ".apng",
    ".avif",
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".webp",
}


@dataclass(frozen=True)
class AttachmentInfo:
    filename: str
    content_type: str | None = None
    url: str | None = None
    local_path: str | None = None

    @property
    def is_image(self) -> bool:
        if (
            self.content_type
            and self.content_type.lower().split(";", 1)[0].strip()
            in RASTER_IMAGE_CONTENT_TYPES
        ):
            return True

        filename = self.filename.lower()
        return any(
            filename.endswith(extension) for extension in RASTER_IMAGE_EXTENSIONS
        )


@dataclass(frozen=True)
class MessageEvent:
    message_id: str
    channel_id: str
    author_id: str
    author_name: str
    content: str
    created_at: datetime
    attachments: list[AttachmentInfo]


@dataclass
class RuntimeState:
    last_owner_message_at: datetime | None = None
    last_proactive_sent_at: datetime | None = None
    unanswered_proactive_count: int = 0
    last_proactive_reason: str = ""
    last_proactive_message: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "last_owner_message_at": _datetime_to_json(self.last_owner_message_at),
            "last_proactive_sent_at": _datetime_to_json(self.last_proactive_sent_at),
            "unanswered_proactive_count": self.unanswered_proactive_count,
            "last_proactive_reason": self.last_proactive_reason,
            "last_proactive_message": self.last_proactive_message,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RuntimeState:
        return cls(
            last_owner_message_at=_datetime_from_json(
                data.get("last_owner_message_at")
            ),
            last_proactive_sent_at=_datetime_from_json(
                data.get("last_proactive_sent_at")
            ),
            unanswered_proactive_count=int(data.get("unanswered_proactive_count", 0)),
            last_proactive_reason=str(data.get("last_proactive_reason", "")),
            last_proactive_message=str(data.get("last_proactive_message", "")),
        )


@dataclass
class MemorySnapshot:
    bot_identity: str
    owner_profile: str
    relationship_journal: str
    avatar_prompt: str
    runtime_state: RuntimeState


@dataclass(frozen=True)
class MemoryUpdate:
    op: str = "add"
    value: str = ""
    find: str | None = None


@dataclass
class AgentResult:
    reply_text: str
    bot_identity_updates: list[MemoryUpdate] = field(default_factory=list)
    owner_profile_updates: list[MemoryUpdate] = field(default_factory=list)
    relationship_journal_updates: list[MemoryUpdate] = field(default_factory=list)
    avatar_updates: list[MemoryUpdate] = field(default_factory=list)
    runtime_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProactiveDecision:
    should_send: bool
    reason: str = ""
    message: str = ""
    skip_reason: str = ""


def _datetime_to_json(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _datetime_from_json(value: object) -> datetime | None:
    if not value:
        return None
    if not isinstance(value, str):
        raise TypeError("datetime values must be ISO 8601 strings")
    return datetime.fromisoformat(value)
