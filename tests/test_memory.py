from datetime import datetime, timezone

from bot.memory.curator import MemoryCurator
from bot.memory.store import MemoryStore
from bot.models import ConversationEntry, MemoryUpdate, RuntimeState


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

    curator.apply_updates(
        owner_profile_updates=[MemoryUpdate(value=" Owner enjoys climbing. ")]
    )

    snapshot = store.load_snapshot()
    assert "- Owner enjoys climbing." in snapshot.owner_profile


def test_memory_curator_rejects_blocked_secret_like_memory(tmp_path):
    store = MemoryStore(tmp_path)
    curator = MemoryCurator(store)

    curator.apply_updates(
        owner_profile_updates=[
            MemoryUpdate(value="api key: sk-fakeplaceholder1234567890")
        ]
    )

    snapshot = store.load_snapshot()
    assert "sk-fakeplaceholder" not in snapshot.owner_profile
    assert "api key" not in snapshot.owner_profile.lower()


def test_memory_curator_normalizes_multiline_updates_and_rejects_long_entries(tmp_path):
    store = MemoryStore(tmp_path)
    curator = MemoryCurator(store)

    curator.apply_updates(
        owner_profile_updates=[
            MemoryUpdate(value="  # Owner\n- Likes   quiet\n\n  evenings.  "),
            MemoryUpdate(value="x" * 501),
        ]
    )

    snapshot = store.load_snapshot()
    assert "- # Owner - Likes quiet evenings." in snapshot.owner_profile
    assert "\n- Likes" not in snapshot.owner_profile
    assert "x" * 501 not in snapshot.owner_profile


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


def test_runtime_state_load_degrades_gracefully_when_json_is_corrupt(tmp_path):
    store = MemoryStore(tmp_path)
    store.load_snapshot()
    runtime_path = tmp_path / "runtime_state.json"
    runtime_path.write_text("{not-json", encoding="utf-8")

    snapshot = store.load_snapshot()

    assert snapshot.runtime_state == RuntimeState()
    assert runtime_path.read_text(encoding="utf-8").startswith("{")


def test_conversation_history_save_load_round_trips_entries(tmp_path):
    store = MemoryStore(tmp_path)
    entry = ConversationEntry(
        role="owner",
        content="你好",
        timestamp=datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc),
    )

    store.save_conversation_history([entry])

    assert store.load_conversation_history() == [entry]


def test_conversation_history_save_truncates_to_last_ten_messages(tmp_path):
    store = MemoryStore(tmp_path)
    entries = [
        ConversationEntry(
            role="owner",
            content=f"message {index}",
            timestamp=datetime(2026, 5, 13, 12, index, tzinfo=timezone.utc),
        )
        for index in range(12)
    ]

    store.save_conversation_history(entries)

    history = store.load_conversation_history()
    assert len(history) == 10
    assert history[0].content == "message 2"
    assert history[-1].content == "message 11"


def test_attachment_metadata_uses_unique_paths_for_repeated_filenames(tmp_path):
    store = MemoryStore(tmp_path)

    first_path = store.save_attachment_metadata(
        "portrait.png", "https://cdn.example.test/a/portrait.png"
    )
    second_path = store.save_attachment_metadata(
        "portrait.png", "https://cdn.example.test/b/portrait.png"
    )

    assert first_path != second_path
    assert first_path.is_file()
    assert second_path.is_file()


def test_memory_curator_skips_duplicate_updates(tmp_path):
    store = MemoryStore(tmp_path)
    curator = MemoryCurator(store)

    curator.apply_updates(
        owner_profile_updates=[MemoryUpdate(value="Owner enjoys climbing.")]
    )
    curator.apply_updates(
        owner_profile_updates=[MemoryUpdate(value="Owner enjoys climbing.")]
    )

    snapshot = store.load_snapshot()
    assert snapshot.owner_profile.count("- Owner enjoys climbing.") == 1


def test_memory_curator_replaces_entire_matching_owner_profile_line(tmp_path):
    store = MemoryStore(tmp_path)
    curator = MemoryCurator(store)
    curator.apply_updates(
        owner_profile_updates=[
            MemoryUpdate(value="Owner likes morning coding with tea.")
        ]
    )

    curator.apply_updates(
        owner_profile_updates=[
            MemoryUpdate(
                op="replace",
                find="morning coding",
                value="Owner prefers coding at night",
            )
        ]
    )

    snapshot = store.load_snapshot()
    assert "- Owner prefers coding at night" in snapshot.owner_profile
    assert "Owner likes morning coding with tea." not in snapshot.owner_profile


def test_memory_curator_removes_entire_matching_owner_profile_line(tmp_path):
    store = MemoryStore(tmp_path)
    curator = MemoryCurator(store)
    curator.apply_updates(
        owner_profile_updates=[
            MemoryUpdate(value="Owner likes puzzle games."),
            MemoryUpdate(value="Owner enjoys late-night tea."),
        ]
    )

    curator.apply_updates(
        owner_profile_updates=[MemoryUpdate(op="remove", find="puzzle games")]
    )

    snapshot = store.load_snapshot()
    assert "Owner likes puzzle games." not in snapshot.owner_profile
    assert "- Owner enjoys late-night tea." in snapshot.owner_profile


def test_memory_curator_ignores_remove_with_blank_find(tmp_path):
    store = MemoryStore(tmp_path)
    curator = MemoryCurator(store)
    store.replace_markdown(
        "owner_profile.md",
        "# Owner Profile\n- Owner   likes puzzle games.\n- Owner enjoys late-night tea.\n",
    )

    curator.apply_updates(
        owner_profile_updates=[MemoryUpdate(op="remove", find="   ")]
    )

    snapshot = store.load_snapshot()
    assert "- Owner   likes puzzle games." in snapshot.owner_profile
    assert "- Owner enjoys late-night tea." in snapshot.owner_profile


def test_memory_curator_ignores_replace_with_blank_find(tmp_path):
    store = MemoryStore(tmp_path)
    curator = MemoryCurator(store)
    curator.apply_updates(
        owner_profile_updates=[
            MemoryUpdate(value="Owner likes morning coding with tea.")
        ]
    )

    curator.apply_updates(
        owner_profile_updates=[
            MemoryUpdate(
                op="replace",
                find="   ",
                value="Owner prefers coding at night",
            )
        ]
    )

    snapshot = store.load_snapshot()
    assert "- Owner likes morning coding with tea." in snapshot.owner_profile
    assert "Owner prefers coding at night" not in snapshot.owner_profile


def test_memory_curator_compacts_near_duplicate_lines(tmp_path):
    store = MemoryStore(tmp_path)
    curator = MemoryCurator(store)

    entries = []
    for i in range(250):
        entries.append(
            MemoryUpdate(value=f"Owner works on project alpha iteration {i}")
        )
    entries.append(MemoryUpdate(value="Owner loves hiking on weekends"))
    entries.append(MemoryUpdate(value="Owner prefers coding at night"))

    curator.apply_updates(owner_profile_updates=entries)

    snapshot = store.load_snapshot()
    lines = snapshot.owner_profile.splitlines()

    bullet_lines = [line for line in lines if line.strip().startswith("- ")]
    assert len(bullet_lines) < 100

    assert any("hiking" in line for line in bullet_lines)
    assert any("coding at night" in line for line in bullet_lines)
