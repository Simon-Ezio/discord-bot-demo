from __future__ import annotations

from bot.memory.store import MemoryStore
from bot.models import MemoryUpdate
from bot.safety import contains_blocked_memory_content


MAX_MEMORY_ENTRY_LENGTH = 500
COMPACTION_MAX_LINES = 200
COMPACTION_MAX_BYTES = 10240
NEAR_DUPLICATE_JACCARD_THRESHOLD = 0.7


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
                self.compact_if_needed(path_name)

    def _replace_or_add(self, lines: list[str], update: MemoryUpdate) -> bool:
        find = self._normalize_find(update.find)
        if not find:
            return False

        value = self._normalize_value(update.value)
        if not self._is_safe_value(value):
            return False

        entry = f"- {value}"
        for index, line in enumerate(lines):
            if find in line:
                if line == entry:
                    return False
                lines[index] = entry
                return True

        return self._add(lines, MemoryUpdate(value=value))

    def _remove(self, lines: list[str], update: MemoryUpdate) -> bool:
        find = self._normalize_find(update.find)
        if not find:
            return False

        original_length = len(lines)
        lines[:] = [line for line in lines if find not in line]
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

    def _normalize_find(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def compact_if_needed(
        self,
        path_name: str,
        *,
        max_lines: int = COMPACTION_MAX_LINES,
        max_bytes: int = COMPACTION_MAX_BYTES,
    ) -> None:
        content = self.store._read_markdown(path_name)
        lines = content.splitlines()
        if len(lines) <= max_lines and len(content.encode("utf-8")) <= max_bytes:
            return

        entry_indices = [
            i for i, line in enumerate(lines)
            if line.strip().startswith("- ")
        ]

        if len(entry_indices) < 2:
            return

        to_remove: set[int] = set()
        for i in range(len(entry_indices)):
            idx_a = entry_indices[i]
            if idx_a in to_remove:
                continue
            norm_a = self._normalize_for_dedup(lines[idx_a])
            for j in range(i + 1, len(entry_indices)):
                idx_b = entry_indices[j]
                if idx_b in to_remove:
                    continue
                norm_b = self._normalize_for_dedup(lines[idx_b])
                if self._is_near_duplicate(norm_a, norm_b):
                    to_remove.add(idx_a)
                    break

        if to_remove:
            compacted = [line for i, line in enumerate(lines) if i not in to_remove]
            self.store.replace_markdown(path_name, "\n".join(compacted) + "\n")

    @staticmethod
    def _normalize_for_dedup(line: str) -> str:
        stripped = line.strip()
        if stripped.startswith("- "):
            stripped = stripped[2:]
        return " ".join(stripped.lower().split())

    @staticmethod
    def _is_near_duplicate(norm_a: str, norm_b: str) -> bool:
        words_a = set(norm_a.split())
        words_b = set(norm_b.split())
        if not words_a or not words_b:
            return False
        intersection = words_a & words_b
        union = words_a | words_b
        jaccard = len(intersection) / len(union)
        return jaccard >= NEAR_DUPLICATE_JACCARD_THRESHOLD

    def _is_safe_value(self, value: str) -> bool:
        return (
            bool(value)
            and len(value) <= MAX_MEMORY_ENTRY_LENGTH
            and not contains_blocked_memory_content(value)
        )
