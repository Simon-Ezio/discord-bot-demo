# Discord Relationship Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python Discord bot that learns its owner through natural conversation, persists evolving identity/relationship state to local files, and can reach out proactively with backoff.

**Architecture:** Use a lightweight Hermes-inspired runtime: Discord adapter -> internal `MessageEvent` -> runtime -> MiniMax relationship agent -> curated file memory -> reply/log send. Keep all state local and all secrets in `.env`.

**Tech Stack:** Python 3.11+, `discord.py`, `python-dotenv`, `httpx`, `pytest`, local Markdown/JSON state files.

---

## File Structure

- Create `pyproject.toml`: package metadata, runtime dependencies, pytest config.
- Create `.env.example`: safe placeholder configuration only.
- Modify `.gitignore`: ensure `.env`, `state/`, downloaded attachments, caches, and virtualenvs are ignored while keeping docs tracked.
- Create `src/bot/config.py`: typed environment loading and validation.
- Create `src/bot/models.py`: dataclasses for events, attachments, memory snapshots, agent results, proactive decisions.
- Create `src/bot/safety.py`: safe mention filtering, secret detection, prompt-injection-ish memory rejection.
- Create `src/bot/memory/store.py`: file-backed state initialization, reads, writes, JSON runtime state.
- Create `src/bot/memory/curator.py`: validated merge logic for identity, owner profile, journal, avatar references.
- Create `src/bot/agent/minimax_client.py`: MiniMax chat client with injectable transport for tests.
- Create `src/bot/agent/prompt_builder.py`: prompt assembly from state snapshots and current message.
- Create `src/bot/agent/relationship_agent.py`: structured response parsing and fallback behavior.
- Create `src/bot/platforms/discord_adapter.py`: Discord client wrapper, filtering, attachment download, safe sends.
- Create `src/bot/observability/bot_logger.py`: local and Discord log-channel summaries.
- Create `src/bot/scheduler/proactive.py`: proactive decision/backoff logic.
- Create `src/bot/runtime.py`: orchestration for inbound messages and proactive sends.
- Create `src/bot/main.py`: application entry point.
- Create `scripts/dry_run_turn.py`: simulate one turn without Discord.
- Create `scripts/show_state.py`: print compact state summary.
- Create tests under `tests/` matching the modules above.

## Task 1: Project Skeleton And Configuration

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Modify: `.gitignore`
- Create: `src/bot/__init__.py`
- Create: `src/bot/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_config.py` with tests for successful env parsing, missing required values, and numeric proactive defaults:

```python
import pytest

from bot.config import BotConfig, ConfigError


def test_config_loads_required_values(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-token")
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("OWNER_USER_ID", "123")
    monkeypatch.setenv("OWNER_USERNAME", "cm6550")
    monkeypatch.setenv("CHAT_CHANNEL_ID", "456")
    monkeypatch.setenv("LOG_CHANNEL_ID", "789")

    config = BotConfig.from_env()

    assert config.discord_bot_token == "discord-token"
    assert config.minimax_api_key == "minimax-key"
    assert config.owner_user_id == "123"
    assert config.owner_username == "cm6550"
    assert config.chat_channel_id == "456"
    assert config.log_channel_id == "789"
    assert config.proactive_check_seconds == 60
    assert config.proactive_min_idle_seconds == 300
    assert config.proactive_max_idle_seconds == 900


def test_config_rejects_missing_required_value(monkeypatch):
    for key in (
        "DISCORD_BOT_TOKEN",
        "MINIMAX_API_KEY",
        "OWNER_USER_ID",
        "CHAT_CHANNEL_ID",
        "LOG_CHANNEL_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigError) as exc:
        BotConfig.from_env()

    assert "DISCORD_BOT_TOKEN" in str(exc.value)


def test_config_rejects_invalid_idle_window(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-token")
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("OWNER_USER_ID", "123")
    monkeypatch.setenv("CHAT_CHANNEL_ID", "456")
    monkeypatch.setenv("LOG_CHANNEL_ID", "789")
    monkeypatch.setenv("PROACTIVE_MIN_IDLE_SECONDS", "900")
    monkeypatch.setenv("PROACTIVE_MAX_IDLE_SECONDS", "300")

    with pytest.raises(ConfigError) as exc:
        BotConfig.from_env()

    assert "PROACTIVE_MIN_IDLE_SECONDS" in str(exc.value)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_config.py -v`

Expected: fail with `ModuleNotFoundError` or missing `BotConfig`.

- [ ] **Step 3: Add project metadata and config implementation**

Create `pyproject.toml` with:

```toml
[project]
name = "discord-relationship-bot"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "discord.py>=2.4.0",
  "httpx>=0.27.0",
  "python-dotenv>=1.0.1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0.0",
]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

Create `.env.example` with:

```text
DISCORD_BOT_TOKEN=
MINIMAX_API_KEY=
OWNER_USER_ID=
OWNER_USERNAME=cm6550
CHAT_CHANNEL_ID=
LOG_CHANNEL_ID=
MINIMAX_BASE_URL=https://api.minimax.chat/v1/text/chatcompletion_v2
MINIMAX_MODEL=
PROACTIVE_CHECK_SECONDS=60
PROACTIVE_MIN_IDLE_SECONDS=300
PROACTIVE_MAX_IDLE_SECONDS=900
STATE_DIR=state
```

Ensure `.gitignore` includes:

```text
.env
state/
*.log
```

Create `src/bot/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class BotConfig:
    discord_bot_token: str
    minimax_api_key: str
    owner_user_id: str
    owner_username: str
    chat_channel_id: str
    log_channel_id: str
    minimax_base_url: str
    minimax_model: str
    proactive_check_seconds: int
    proactive_min_idle_seconds: int
    proactive_max_idle_seconds: int
    state_dir: Path

    @classmethod
    def from_env(cls) -> "BotConfig":
        load_dotenv()
        required = {
            "DISCORD_BOT_TOKEN": os.getenv("DISCORD_BOT_TOKEN", "").strip(),
            "MINIMAX_API_KEY": os.getenv("MINIMAX_API_KEY", "").strip(),
            "OWNER_USER_ID": os.getenv("OWNER_USER_ID", "").strip(),
            "CHAT_CHANNEL_ID": os.getenv("CHAT_CHANNEL_ID", "").strip(),
            "LOG_CHANNEL_ID": os.getenv("LOG_CHANNEL_ID", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ConfigError(f"Missing required environment values: {', '.join(missing)}")

        check_seconds = _env_int("PROACTIVE_CHECK_SECONDS", 60)
        min_idle = _env_int("PROACTIVE_MIN_IDLE_SECONDS", 300)
        max_idle = _env_int("PROACTIVE_MAX_IDLE_SECONDS", 900)
        if min_idle > max_idle:
            raise ConfigError("PROACTIVE_MIN_IDLE_SECONDS must be <= PROACTIVE_MAX_IDLE_SECONDS")

        return cls(
            discord_bot_token=required["DISCORD_BOT_TOKEN"],
            minimax_api_key=required["MINIMAX_API_KEY"],
            owner_user_id=required["OWNER_USER_ID"],
            owner_username=os.getenv("OWNER_USERNAME", "owner").strip() or "owner",
            chat_channel_id=required["CHAT_CHANNEL_ID"],
            log_channel_id=required["LOG_CHANNEL_ID"],
            minimax_base_url=os.getenv(
                "MINIMAX_BASE_URL",
                "https://api.minimax.chat/v1/text/chatcompletion_v2",
            ).strip(),
            minimax_model=os.getenv("MINIMAX_MODEL", "").strip(),
            proactive_check_seconds=check_seconds,
            proactive_min_idle_seconds=min_idle,
            proactive_max_idle_seconds=max_idle,
            state_dir=Path(os.getenv("STATE_DIR", "state")).expanduser(),
        )


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be positive")
    return value
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_config.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example .gitignore src/bot/__init__.py src/bot/config.py tests/test_config.py
git commit -m "chore: add bot project configuration"
```

## Task 2: Event Models And Safety Helpers

**Files:**
- Create: `src/bot/models.py`
- Create: `src/bot/safety.py`
- Test: `tests/test_models_safety.py`

- [ ] **Step 1: Write failing tests**

Create tests that verify owner/channel filtering inputs can be represented, unsafe mentions are neutralized, and secret-like memory text is rejected:

```python
from datetime import UTC, datetime

from bot.models import AttachmentInfo, MessageEvent
from bot.safety import contains_blocked_memory_content, sanitize_discord_output


def test_message_event_owner_channel_shape():
    event = MessageEvent(
        message_id="m1",
        channel_id="chat",
        author_id="owner",
        author_name="cm6550",
        content="hello",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
        attachments=[AttachmentInfo(filename="avatar.png", content_type="image/png", url="https://cdn.example/avatar.png")],
    )

    assert event.author_id == "owner"
    assert event.attachments[0].is_image


def test_sanitize_discord_output_blocks_mass_mentions():
    assert "@\u200beveryone" in sanitize_discord_output("@everyone hi")
    assert "@\u200bhere" in sanitize_discord_output("@here hi")


def test_contains_blocked_memory_content_detects_secrets():
    assert contains_blocked_memory_content("DISCORD_BOT_TOKEN=abc")
    assert contains_blocked_memory_content("MINIMAX_API_KEY=redacted")
    assert not contains_blocked_memory_content("Owner enjoys climbing.")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_models_safety.py -v`

Expected: fail because modules are missing.

- [ ] **Step 3: Implement models and safety**

Create `src/bot/models.py` with dataclasses for `AttachmentInfo`, `MessageEvent`, `MemorySnapshot`, `RuntimeState`, `AgentResult`, and `ProactiveDecision`.

Create `src/bot/safety.py` with:

```python
from __future__ import annotations

import re

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"DISCORD_BOT_TOKEN\s*=", re.IGNORECASE),
    re.compile(r"MINIMAX_API_KEY\s*=", re.IGNORECASE),
    re.compile(r"ignore\s+(all|previous|prior)\s+instructions", re.IGNORECASE),
]


def sanitize_discord_output(text: str) -> str:
    return (
        text.replace("@everyone", "@\u200beveryone")
        .replace("@here", "@\u200bhere")
    )


def contains_blocked_memory_content(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_models_safety.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bot/models.py src/bot/safety.py tests/test_models_safety.py
git commit -m "feat: add bot event models and safety helpers"
```

## Task 3: File-Backed Memory Store And Curator

**Files:**
- Create: `src/bot/memory/__init__.py`
- Create: `src/bot/memory/store.py`
- Create: `src/bot/memory/curator.py`
- Test: `tests/test_memory.py`

- [ ] **Step 1: Write failing tests**

Cover initial file creation, snapshot reads, runtime state updates, deduplication, and blocked secret writes.

```python
from bot.memory.curator import MemoryCurator
from bot.memory.store import MemoryStore


def test_store_initializes_state_files(tmp_path):
    store = MemoryStore(tmp_path)
    snapshot = store.load_snapshot()

    assert "not yet formed" in snapshot.bot_identity.lower()
    assert (tmp_path / "bot_identity.md").exists()
    assert (tmp_path / "owner_profile.md").exists()
    assert snapshot.runtime_state.unanswered_proactive_count == 0


def test_curator_appends_safe_owner_memory(tmp_path):
    store = MemoryStore(tmp_path)
    curator = MemoryCurator(store)

    curator.apply_updates(owner_profile_updates=["Owner enjoys climbing."])
    snapshot = store.load_snapshot()

    assert "Owner enjoys climbing." in snapshot.owner_profile


def test_curator_rejects_secret_memory(tmp_path):
    store = MemoryStore(tmp_path)
    curator = MemoryCurator(store)

    curator.apply_updates(owner_profile_updates=["MINIMAX_API_KEY=redacted"])
    snapshot = store.load_snapshot()

    assert "MINIMAX_API_KEY" not in snapshot.owner_profile
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_memory.py -v`

Expected: fail because memory modules are missing.

- [ ] **Step 3: Implement memory files and merge logic**

Implement `MemoryStore` with methods:

- `load_snapshot() -> MemorySnapshot`
- `append_markdown(path_name: str, entries: list[str]) -> None`
- `replace_markdown(path_name: str, content: str) -> None`
- `save_runtime_state(state: RuntimeState) -> None`
- `save_attachment_metadata(filename: str, source_url: str) -> Path`

Implement atomic writes using `tempfile.NamedTemporaryFile` in the state directory and `Path.replace()`.

Implement `MemoryCurator.apply_updates()` with explicit optional lists:

```python
def apply_updates(
    self,
    *,
    bot_identity_updates: list[str] | None = None,
    owner_profile_updates: list[str] | None = None,
    relationship_journal_updates: list[str] | None = None,
    avatar_updates: list[str] | None = None,
) -> None:
    ...
```

The curator should strip whitespace, skip duplicates already present in target files, reject blocked content via `contains_blocked_memory_content()`, and append safe entries under Markdown bullets.

- [ ] **Step 4: Run memory tests**

Run: `pytest tests/test_memory.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bot/memory tests/test_memory.py
git commit -m "feat: add file backed relationship memory"
```

## Task 4: MiniMax Client, Prompt Builder, And Agent Parsing

**Files:**
- Create: `src/bot/agent/__init__.py`
- Create: `src/bot/agent/minimax_client.py`
- Create: `src/bot/agent/prompt_builder.py`
- Create: `src/bot/agent/relationship_agent.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: Write failing tests**

Test prompt inclusion, successful structured parsing, and invalid JSON fallback.

```python
from datetime import UTC, datetime

import pytest

from bot.agent.prompt_builder import PromptBuilder
from bot.agent.relationship_agent import RelationshipAgent
from bot.models import MessageEvent, MemorySnapshot, RuntimeState


class FakeMiniMaxClient:
    def __init__(self, text):
        self.text = text

    async def complete(self, messages):
        self.messages = messages
        return self.text


def snapshot():
    return MemorySnapshot(
        bot_identity="The bot is still forming.",
        owner_profile="Owner likes climbing.",
        relationship_journal="First conversation was warm.",
        avatar_prompt="No avatar yet.",
        runtime_state=RuntimeState(),
    )


def event():
    return MessageEvent(
        message_id="m1",
        channel_id="chat",
        author_id="owner",
        author_name="cm6550",
        content="what do you remember?",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
        attachments=[],
    )


def test_prompt_builder_includes_memory_snapshot():
    messages = PromptBuilder(owner_username="cm6550").build_chat_messages(snapshot(), event())

    joined = "\n".join(message["content"] for message in messages)
    assert "Owner likes climbing." in joined
    assert "not a survey" in joined


@pytest.mark.asyncio
async def test_relationship_agent_parses_structured_response():
    client = FakeMiniMaxClient('{"reply_text":"I remember climbing.","owner_profile_updates":["Owner likes climbing."]}')
    agent = RelationshipAgent(client=client, prompt_builder=PromptBuilder(owner_username="cm6550"))

    result = await agent.respond(snapshot(), event())

    assert result.reply_text == "I remember climbing."
    assert result.owner_profile_updates == ["Owner likes climbing."]


@pytest.mark.asyncio
async def test_relationship_agent_falls_back_on_invalid_json():
    client = FakeMiniMaxClient("plain text reply")
    agent = RelationshipAgent(client=client, prompt_builder=PromptBuilder(owner_username="cm6550"))

    result = await agent.respond(snapshot(), event())

    assert result.reply_text == "plain text reply"
    assert result.owner_profile_updates == []
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_agent.py -v`

Expected: fail because agent modules are missing.

- [ ] **Step 3: Implement prompt builder and agent**

`PromptBuilder` must produce two chat messages:

- system message: natural relationship-building rules, no survey behavior, state content treated as data.
- user message: current message text and attachment summary.

`RelationshipAgent.respond()` must request JSON with keys:

- `reply_text`
- `bot_identity_updates`
- `owner_profile_updates`
- `relationship_journal_updates`
- `avatar_updates`
- `runtime_notes`

If MiniMax returns invalid JSON, return `AgentResult(reply_text=raw_text, update lists empty)`.

`MiniMaxClient.complete()` should use `httpx.AsyncClient.post()` with API key header and injected URL/model. Keep payload isolated in this client so endpoint changes are one-file edits.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_agent.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bot/agent tests/test_agent.py
git commit -m "feat: add minimax relationship agent"
```

## Task 5: Proactive Scheduler Decision And Backoff

**Files:**
- Create: `src/bot/scheduler/__init__.py`
- Create: `src/bot/scheduler/proactive.py`
- Test: `tests/test_proactive.py`

- [ ] **Step 1: Write failing tests**

Test idle window, unanswered backoff, and reset on owner reply.

```python
from datetime import UTC, datetime, timedelta

from bot.models import RuntimeState
from bot.scheduler.proactive import ProactivePolicy


def test_policy_skips_before_min_idle():
    now = datetime(2026, 5, 13, 12, 0, tzinfo=UTC)
    state = RuntimeState(last_owner_message_at=now - timedelta(seconds=120))

    decision = ProactivePolicy(min_idle_seconds=300, max_idle_seconds=900).precheck(state, now)

    assert decision.allowed is False
    assert "idle" in decision.reason


def test_policy_allows_inside_idle_window():
    now = datetime(2026, 5, 13, 12, 0, tzinfo=UTC)
    state = RuntimeState(last_owner_message_at=now - timedelta(seconds=600))

    decision = ProactivePolicy(min_idle_seconds=300, max_idle_seconds=900).precheck(state, now)

    assert decision.allowed is True


def test_policy_applies_unanswered_backoff():
    now = datetime(2026, 5, 13, 12, 0, tzinfo=UTC)
    state = RuntimeState(
        last_owner_message_at=now - timedelta(seconds=600),
        last_proactive_sent_at=now - timedelta(seconds=300),
        unanswered_proactive_count=2,
    )

    decision = ProactivePolicy(min_idle_seconds=300, max_idle_seconds=900).precheck(state, now)

    assert decision.allowed is False
    assert "backoff" in decision.reason
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_proactive.py -v`

Expected: fail because scheduler module is missing.

- [ ] **Step 3: Implement proactive policy**

Implement:

- `ProactivePolicy.precheck(state, now) -> PrecheckDecision`
- backoff seconds as `min_idle_seconds * (2 ** unanswered_proactive_count)`
- skip if no prior owner message exists
- skip if current idle is below `min_idle_seconds`
- allow inside idle window unless backoff is active
- allow after `max_idle_seconds` only if backoff is not active

Implement a `ProactivePlanner` that calls `RelationshipAgent.plan_proactive()` later in Task 7.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_proactive.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bot/scheduler tests/test_proactive.py
git commit -m "feat: add proactive outreach policy"
```

## Task 6: Discord Adapter, Logging, And Runtime

**Files:**
- Create: `src/bot/platforms/__init__.py`
- Create: `src/bot/platforms/discord_adapter.py`
- Create: `src/bot/observability/__init__.py`
- Create: `src/bot/observability/bot_logger.py`
- Create: `src/bot/runtime.py`
- Test: `tests/test_runtime.py`
- Test: `tests/test_discord_adapter.py`

- [ ] **Step 1: Write failing runtime tests**

Use fake adapter/agent/store objects to verify one inbound message sends a reply, applies memory updates, and updates runtime state.

```python
from datetime import UTC, datetime

import pytest

from bot.models import AgentResult, MessageEvent, MemorySnapshot, RuntimeState
from bot.runtime import BotRuntime


class FakeStore:
    def __init__(self):
        self.saved_state = None

    def load_snapshot(self):
        return MemorySnapshot("", "", "", "", RuntimeState())

    def save_runtime_state(self, state):
        self.saved_state = state


class FakeCurator:
    def __init__(self):
        self.called = False

    def apply_updates(self, **kwargs):
        self.called = True


class FakeAgent:
    async def respond(self, snapshot, event):
        return AgentResult(reply_text="hello owner", owner_profile_updates=["Owner greeted the bot."])


class FakeAdapter:
    def __init__(self):
        self.sent = []

    async def send_chat(self, text):
        self.sent.append(text)


class FakeLogger:
    async def info(self, message):
        self.last = message


@pytest.mark.asyncio
async def test_runtime_handles_owner_message():
    store = FakeStore()
    curator = FakeCurator()
    adapter = FakeAdapter()
    runtime = BotRuntime(store=store, curator=curator, agent=FakeAgent(), adapter=adapter, logger=FakeLogger())
    event = MessageEvent("m1", "chat", "owner", "cm6550", "hi", datetime(2026, 5, 13, tzinfo=UTC), [])

    await runtime.handle_message(event)

    assert adapter.sent == ["hello owner"]
    assert curator.called is True
    assert store.saved_state.last_owner_message_at == event.created_at
```

- [ ] **Step 2: Write failing adapter filter tests**

Test a pure helper such as `should_accept_message(author_id, channel_id, is_bot, is_dm, config)`.

```python
from bot.platforms.discord_adapter import should_accept_message


class Config:
    owner_user_id = "owner"
    chat_channel_id = "chat"


def test_accepts_only_owner_in_chat_channel():
    assert should_accept_message("owner", "chat", False, False, Config()) is True
    assert should_accept_message("other", "chat", False, False, Config()) is False
    assert should_accept_message("owner", "other", False, False, Config()) is False
    assert should_accept_message("owner", "chat", True, False, Config()) is False
    assert should_accept_message("owner", "chat", False, True, Config()) is False
```

- [ ] **Step 3: Run tests to verify failure**

Run: `pytest tests/test_runtime.py tests/test_discord_adapter.py -v`

Expected: fail because runtime/adapter modules are missing.

- [ ] **Step 4: Implement runtime and adapter boundary**

Implement `BotRuntime.handle_message()`:

- load snapshot
- call `agent.respond(snapshot, event)`
- send sanitized reply through adapter
- apply memory updates through curator
- update `runtime_state.last_owner_message_at`
- clear `unanswered_proactive_count`
- log safe summary

Implement `should_accept_message()` exactly against configured owner/channel/bot/DM flags.

Implement `DiscordAdapter` with:

- `on_message` conversion to `MessageEvent`
- `send_chat(text)`
- `send_log(text)`
- `download_image_attachments(message)`
- `discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=True)`

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_runtime.py tests/test_discord_adapter.py -v`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/bot/platforms src/bot/observability src/bot/runtime.py tests/test_runtime.py tests/test_discord_adapter.py
git commit -m "feat: connect runtime to discord adapter boundary"
```

## Task 7: Entry Point, Scripts, And End-To-End Verification

**Files:**
- Create: `src/bot/main.py`
- Create: `scripts/dry_run_turn.py`
- Create: `scripts/show_state.py`
- Create: `README.md`
- Test: `tests/test_scripts.py`

- [ ] **Step 1: Write failing script tests**

Test that dry-run can run with a fake agent and show-state can summarize initialized files.

```python
import subprocess
import sys


def test_show_state_help_runs():
    result = subprocess.run([sys.executable, "scripts/show_state.py", "--help"], text=True, capture_output=True)

    assert result.returncode == 0
    assert "state" in result.stdout.lower()


def test_dry_run_help_runs():
    result = subprocess.run([sys.executable, "scripts/dry_run_turn.py", "--help"], text=True, capture_output=True)

    assert result.returncode == 0
    assert "message" in result.stdout.lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_scripts.py -v`

Expected: fail because scripts are missing.

- [ ] **Step 3: Implement entry point and scripts**

`main.py` should:

- load `BotConfig.from_env()`
- create `MemoryStore`, `MemoryCurator`, `MiniMaxClient`, `PromptBuilder`, `RelationshipAgent`, `BotLogger`, `BotRuntime`, `DiscordAdapter`
- start Discord client
- start proactive loop as an asyncio task after `on_ready`

`dry_run_turn.py` should:

- accept `--message`
- load config/state
- create a synthetic owner `MessageEvent`
- run `BotRuntime.handle_message()` with a console adapter

`show_state.py` should:

- accept `--state-dir`
- print compact sections for bot identity, owner profile, avatar, and runtime JSON

`README.md` should include:

- setup commands
- `.env` variable explanation
- Discord developer mode instructions for `OWNER_USER_ID`, `CHAT_CHANNEL_ID`, `LOG_CHANNEL_ID`
- run command
- manual verification checklist

- [ ] **Step 4: Run unit tests**

Run: `pytest -v`

Expected: all tests pass.

- [ ] **Step 5: Run local dry-run**

Run: `python scripts/dry_run_turn.py --message "hi, let's meet"`

Expected: prints a reply or a clear MiniMax configuration/runtime error without writing secrets to output.

- [ ] **Step 6: Run manual Discord verification**

Run the bot:

```bash
python -m bot.main
```

Verify:

- bot logs startup in `#bot-logs`
- owner message in `#chat` receives a reply
- non-owner message is ignored
- message in another channel is ignored
- image upload in avatar context creates an avatar reference
- `state/bot_identity.md` and `state/owner_profile.md` are updated
- idle period triggers a logged proactive decision

- [ ] **Step 7: Commit**

```bash
git add src/bot/main.py scripts/dry_run_turn.py scripts/show_state.py README.md tests/test_scripts.py
git commit -m "feat: add runnable discord relationship bot"
```

## Self-Review Notes

- Spec coverage: channel/owner filtering is covered by Task 6; local config and secret handling by Task 1; file memory by Task 3; MiniMax responses by Task 4; proactive behavior by Task 5; Discord runtime and logs by Tasks 6 and 7; scripts and manual verification by Task 7.
- Scope check: this is one cohesive first version. Multi-owner support, database storage, UI, automatic avatar mutation, and image generation are explicitly out of scope.
- Type consistency: `MessageEvent`, `MemorySnapshot`, `RuntimeState`, `AgentResult`, and `ProactiveDecision` are introduced before dependent runtime/agent tasks.
