from __future__ import annotations

import hashlib
import json
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from bot.models import ConversationEntry, MemorySnapshot, RuntimeState


DEFAULT_BOT_IDENTITY = (
    "# Bot Identity\n\n"
    "- The bot's personality is not yet formed and should develop through safe "
    "memories over time.\n"
)
DEFAULT_OWNER_PROFILE = "# Owner Profile\n"
DEFAULT_RELATIONSHIP_JOURNAL = "# Relationship Journal\n"
DEFAULT_AVATAR_PROMPT = "# Avatar Prompt\n"
MAX_CONVERSATION_HISTORY_MESSAGES = 10
CONVERSATION_HISTORY_FILE = "conversation_history.json"
EVENTS_FILE = "events.jsonl"


class MemoryStore:
    def __init__(self, state_dir: Path | str):
        self.state_dir = Path(state_dir)
        self.attachments_dir = self.state_dir / "attachments"

    def load_snapshot(self) -> MemorySnapshot:
        self._ensure_state_files()
        return MemorySnapshot(
            bot_identity=self._read_markdown("bot_identity.md"),
            owner_profile=self._read_markdown("owner_profile.md"),
            relationship_journal=self._read_markdown("relationship_journal.md"),
            avatar_prompt=self._read_markdown("avatar_prompt.md"),
            runtime_state=self._load_runtime_state(),
            conversation_history=self.load_conversation_history(),
        )

    def append_markdown(self, path_name: str, entries: list[str]) -> None:
        if not entries:
            return

        self._ensure_state_files()
        path = self._state_file(path_name)
        content = path.read_text(encoding="utf-8")
        if content and not content.endswith("\n"):
            content += "\n"
        content += "\n".join(entries) + "\n"
        self._atomic_write(path, content)

    def replace_markdown(self, path_name: str, content: str) -> None:
        self._ensure_state_files()
        self._atomic_write(self._state_file(path_name), content)

    def save_runtime_state(self, state: RuntimeState) -> None:
        self._ensure_state_files()
        content = json.dumps(state.to_json(), indent=2, sort_keys=True) + "\n"
        self._atomic_write(self.state_dir / "runtime_state.json", content)

    def load_conversation_history(self) -> list[ConversationEntry]:
        self._ensure_state_files()
        path = self.state_dir / CONVERSATION_HISTORY_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        if not isinstance(data, list):
            return []

        history: list[ConversationEntry] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                history.append(ConversationEntry.from_json(item))
            except (TypeError, ValueError):
                continue
        return history[-MAX_CONVERSATION_HISTORY_MESSAGES:]

    def save_conversation_history(self, history: list[ConversationEntry]) -> None:
        self._ensure_state_files()
        capped_history = history[-MAX_CONVERSATION_HISTORY_MESSAGES:]
        content = (
            json.dumps(
                [entry.to_json() for entry in capped_history],
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        self._atomic_write(self.state_dir / CONVERSATION_HISTORY_FILE, content)

    def save_attachment_metadata(self, filename: str, source_url: str) -> Path:
        self._ensure_state_files()
        content = (
            json.dumps(
                {"filename": filename, "source_url": source_url},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        metadata_path = self._unique_attachment_metadata_path(
            filename, content, source_url
        )
        self._atomic_write(metadata_path, content)
        return metadata_path

    def _ensure_state_files(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.attachments_dir.mkdir(exist_ok=True)

        defaults = {
            "bot_identity.md": DEFAULT_BOT_IDENTITY,
            "owner_profile.md": DEFAULT_OWNER_PROFILE,
            "relationship_journal.md": DEFAULT_RELATIONSHIP_JOURNAL,
            "avatar_prompt.md": DEFAULT_AVATAR_PROMPT,
        }
        for filename, content in defaults.items():
            path = self.state_dir / filename
            if not path.exists():
                self._atomic_write(path, content)

        runtime_path = self.state_dir / "runtime_state.json"
        if not runtime_path.exists():
            self._atomic_write(runtime_path, json.dumps(RuntimeState().to_json()) + "\n")

        history_path = self.state_dir / CONVERSATION_HISTORY_FILE
        if not history_path.exists():
            self._atomic_write(history_path, "[]\n")

        events_path = self.state_dir / EVENTS_FILE
        if not events_path.exists():
            events_path.write_text("", encoding="utf-8")

    def _read_markdown(self, path_name: str) -> str:
        return self._state_file(path_name).read_text(encoding="utf-8")

    def _load_runtime_state(self) -> RuntimeState:
        runtime_path = self.state_dir / "runtime_state.json"
        try:
            data = json.loads(runtime_path.read_text(encoding="utf-8"))
            return RuntimeState.from_json(data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError, AttributeError):
            state = RuntimeState()
            self.save_runtime_state(state)
            return state

    def _state_file(self, path_name: str) -> Path:
        path = self.state_dir / path_name
        if path.parent != self.state_dir:
            raise ValueError(f"memory path must be a state file name: {path_name}")
        return path

    def _unique_attachment_metadata_path(
        self, filename: str, content: str, source_url: str
    ) -> Path:
        basename = Path(filename).name or "attachment"
        sanitized_basename = re.sub(r"[^A-Za-z0-9_.-]+", "_", basename).strip("._")
        if not sanitized_basename:
            sanitized_basename = "attachment"

        url_hash = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:10]
        stem = f"{sanitized_basename}-{url_hash}"
        candidate = self.attachments_dir / f"{stem}.json"
        counter = 1
        while candidate.exists():
            if candidate.read_text(encoding="utf-8") == content:
                counter += 1
                candidate = self.attachments_dir / f"{stem}-{counter}.json"
                continue
            counter += 1
            candidate = self.attachments_dir / f"{stem}-{counter}.json"
        return candidate

    def append_event(
        self,
        event_type: str,
        summary: str,
        *,
        at: datetime | None = None,
        **extra: str,
    ) -> None:
        self._ensure_state_files()
        timestamp = (at or datetime.now(UTC)).isoformat()
        entry: dict[str, str] = {
            "type": event_type,
            "at": timestamp,
            "summary": summary,
        }
        entry.update(extra)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(self.state_dir / EVENTS_FILE, "a", encoding="utf-8") as fh:
            fh.write(line)

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                delete=False,
            ) as temp_file:
                temp_file.write(content)
                temp_path = Path(temp_file.name)
            temp_path.replace(path)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()
