from __future__ import annotations

from bot.memory.store import MemoryStore
from bot.models import MemoryUpdate
from bot.safety import contains_blocked_memory_content


MAX_MEMORY_ENTRY_LENGTH = 500


class MemoryCurator:
    def __init__(self, store: MemoryStore):
        self.store = store

    def apply_updates(
        self,
        *,
        bot_identity_updates: list[MemoryUpdate] | None = None,
        owner_profile_updates: list[MemoryUpdate] | None = None,
        relationship_journal_updates: list[MemoryUpdate] | None = None,
        avatar_updates: list[MemoryUpdate] | None = None,
    ) -> None:
        update_groups = {
            "bot_identity.md": bot_identity_updates,
            "owner_profile.md": owner_profile_updates,
            "relationship_journal.md": relationship_journal_updates,
            "avatar_prompt.md": avatar_updates,
        }

        snapshot = self.store.load_snapshot()
        existing_content = {
            "bot_identity.md": snapshot.bot_identity,
            "owner_profile.md": snapshot.owner_profile,
            "relationship_journal.md": snapshot.relationship_journal,
            "avatar_prompt.md": snapshot.avatar_prompt,
        }

        for path_name, updates in update_groups.items():
            content = existing_content[path_name]
            lines = content.splitlines()
            changed = False

            for update in updates or []:
                if update.op == "replace":
                    changed = self._replace_or_add(lines, update) or changed
                elif update.op == "remove":
                    changed = self._remove(lines, update) or changed
                else:
                    changed = self._add(lines, update) or changed

            if changed:
                self.store.replace_markdown(path_name, "\n".join(lines) + "\n")

    def _replace_or_add(self, lines: list[str], update: MemoryUpdate) -> bool:
        if not update.find:
            return False

        value = self._normalize_value(update.value)
        if not self._is_safe_value(value):
            return False

        entry = f"- {value}"
        for index, line in enumerate(lines):
            if update.find in line:
                if line == entry:
                    return False
                lines[index] = entry
                return True

        return self._add(lines, MemoryUpdate(value=value))

    def _remove(self, lines: list[str], update: MemoryUpdate) -> bool:
        if not update.find:
            return False

        original_length = len(lines)
        lines[:] = [line for line in lines if update.find not in line]
        return len(lines) != original_length

    def _add(self, lines: list[str], update: MemoryUpdate) -> bool:
        value = self._normalize_value(update.value)
        if not self._is_safe_value(value):
            return False

        entry = f"- {value}"
        if entry in lines:
            return False

        lines.append(entry)
        return True

    def _normalize_value(self, value: str) -> str:
        return " ".join(value.strip().split())

    def _is_safe_value(self, value: str) -> bool:
        return (
            bool(value)
            and len(value) <= MAX_MEMORY_ENTRY_LENGTH
            and not contains_blocked_memory_content(value)
        )
