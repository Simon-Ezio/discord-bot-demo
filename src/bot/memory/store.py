from __future__ import annotations

import json
import tempfile
from pathlib import Path

from bot.models import MemorySnapshot, RuntimeState


DEFAULT_BOT_IDENTITY = (
    "# Bot Identity\n\n"
    "- The bot's personality is not yet formed and should develop through safe "
    "memories over time.\n"
)
DEFAULT_OWNER_PROFILE = "# Owner Profile\n"
DEFAULT_RELATIONSHIP_JOURNAL = "# Relationship Journal\n"
DEFAULT_AVATAR_PROMPT = "# Avatar Prompt\n"


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

    def save_attachment_metadata(self, filename: str, source_url: str) -> Path:
        self._ensure_state_files()
        metadata_path = self.attachments_dir / f"{Path(filename).name}.json"
        content = (
            json.dumps(
                {"filename": filename, "source_url": source_url},
                indent=2,
                sort_keys=True,
            )
            + "\n"
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

    def _read_markdown(self, path_name: str) -> str:
        return self._state_file(path_name).read_text(encoding="utf-8")

    def _load_runtime_state(self) -> RuntimeState:
        runtime_path = self.state_dir / "runtime_state.json"
        data = json.loads(runtime_path.read_text(encoding="utf-8"))
        return RuntimeState.from_json(data)

    def _state_file(self, path_name: str) -> Path:
        path = self.state_dir / path_name
        if path.parent != self.state_dir:
            raise ValueError(f"memory path must be a state file name: {path_name}")
        return path

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
