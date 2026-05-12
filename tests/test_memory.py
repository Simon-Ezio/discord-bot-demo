from datetime import datetime, timezone

from bot.memory.curator import MemoryCurator
from bot.memory.store import MemoryStore
from bot.models import RuntimeState


def test_memory_store_initializes_state_files_and_snapshot_defaults(tmp_path):
    store = MemoryStore(tmp_path / "state")

    snapshot = store.load_snapshot()

    assert "not yet formed" in snapshot.bot_identity
    assert snapshot.runtime_state.unanswered_proactive_count == 0
    assert (tmp_path / "state" / "bot_identity.md").is_file()
    assert (tmp_path / "state" / "owner_profile.md").is_file()
    assert (tmp_path / "state" / "relationship_journal.md").is_file()
    assert (tmp_path / "state" / "avatar_prompt.md").is_file()
    assert (tmp_path / "state" / "runtime_state.json").is_file()
    assert (tmp_path / "state" / "attachments").is_dir()


def test_memory_curator_appends_safe_owner_profile_memory(tmp_path):
    store = MemoryStore(tmp_path)
    curator = MemoryCurator(store)

    curator.apply_updates(owner_profile_updates=[" Owner enjoys climbing. "])

    snapshot = store.load_snapshot()
    assert "- Owner enjoys climbing." in snapshot.owner_profile


def test_memory_curator_rejects_blocked_secret_like_memory(tmp_path):
    store = MemoryStore(tmp_path)
    curator = MemoryCurator(store)

    curator.apply_updates(owner_profile_updates=["api key: sk-fakeplaceholder1234567890"])

    snapshot = store.load_snapshot()
    assert "sk-fakeplaceholder" not in snapshot.owner_profile
    assert "api key" not in snapshot.owner_profile.lower()


def test_runtime_state_save_load_round_trips_key_fields(tmp_path):
    store = MemoryStore(tmp_path)
    last_owner_message_at = datetime(2026, 5, 13, 12, 30, tzinfo=timezone.utc)
    state = RuntimeState(
        last_owner_message_at=last_owner_message_at,
        unanswered_proactive_count=3,
    )

    store.save_runtime_state(state)

    snapshot = store.load_snapshot()
    assert snapshot.runtime_state.last_owner_message_at == last_owner_message_at
    assert snapshot.runtime_state.unanswered_proactive_count == 3


def test_memory_curator_skips_duplicate_updates(tmp_path):
    store = MemoryStore(tmp_path)
    curator = MemoryCurator(store)

    curator.apply_updates(owner_profile_updates=["Owner enjoys climbing."])
    curator.apply_updates(owner_profile_updates=["Owner enjoys climbing."])

    snapshot = store.load_snapshot()
    assert snapshot.owner_profile.count("- Owner enjoys climbing.") == 1
