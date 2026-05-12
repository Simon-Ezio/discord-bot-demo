from __future__ import annotations

from bot.memory.store import MemoryStore
from bot.safety import contains_blocked_memory_content


MAX_MEMORY_ENTRY_LENGTH = 500


class MemoryCurator:
    def __init__(self, store: MemoryStore):
        self.store = store

    def apply_updates(
        self,
        *,
        bot_identity_updates: list[str] | None = None,
        owner_profile_updates: list[str] | None = None,
        relationship_journal_updates: list[str] | None = None,
        avatar_updates: list[str] | None = None,
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
            entries: list[str] = []
            seen_content = existing_content[path_name]
            for update in updates or []:
                value = self._normalize_update(update)
                if (
                    not value
                    or len(value) > MAX_MEMORY_ENTRY_LENGTH
                    or contains_blocked_memory_content(value)
                ):
                    continue

                entry = f"- {value}"
                if entry in seen_content or entry in entries:
                    continue

                entries.append(entry)
                seen_content += f"\n{entry}"

            self.store.append_markdown(path_name, entries)

    def _normalize_update(self, update: str) -> str:
        return " ".join(update.strip().split())
