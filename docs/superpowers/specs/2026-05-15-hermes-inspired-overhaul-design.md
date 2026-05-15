# Hermes-Inspired Overhaul Design

## Goal

Improve the Discord relationship bot's conversation quality and memory architecture by borrowing key patterns from Hermes Agent — specifically: layered system prompts, memory replace/remove operations, conversation history, and better proactive timing.

## 1. Layered System Prompt

**Current**: Single flat string concatenated with stage guidance.

**New**: Five distinct layers, each with a clear responsibility:

| Layer | Content | When it changes |
|---|---|---|
| Identity | Bot identity description (SOUL or default) | Rarely — only when identity matures |
| Behavior rules | How to talk, how to remember, identity/avatar guidance, output format | Never (static) |
| Stage guidance | Dynamic based on current memory state | Every turn (computed from snapshot) |
| Memory snapshot | bot_identity.md, owner_profile.md, relationship_journal.md, avatar_prompt.md | Frozen at session start; live state is written to disk but prompt stays stable |
| Conversation history | Last N messages between owner and bot | Every turn (grows) |
| Current message | The owner's latest message + timestamp + attachments | Every turn |

**Why frozen snapshot**: The memory snapshot injected into the system prompt reflects the state at the beginning of a session. Mid-session writes update the files on disk but do NOT mutate the running system prompt. This keeps the prompt prefix stable (good for LLM caching) and prevents the bot from self-referencing updates it just made in the same turn.

### Implementation

Refactor `PromptBuilder.build_chat_messages()` into separate methods:

- `_build_identity_prompt(snapshot)` — reads bot_identity, returns identity description
- `_build_behavior_prompt()` — static behavioral rules (no args)
- `_build_stage_guidance(snapshot)` — current logic, already exists
- `_build_memory_snapshot(snapshot)` — formats the 4 markdown files
- `_build_history_prompt(history)` — formats recent conversation history
- `_build_current_message_prompt(event)` — the owner's message

The `SessionHistory` class (new) manages the in-memory conversation history and persists it to `conversation_history.json`.

## 2. Memory Operations: add / replace / remove

**Current**: Curator only appends bullet points. No way to update, correct, or remove stale entries.

**New**: Three operations supported in all `*_updates` fields:

```json
{
  "bot_identity_updates": [
    {"op": "replace", "find": "personality not yet formed", "value": "warm and curious, named Nova"},
    {"op": "add", "value": "Enjoys philosophical conversations"}
  ],
  "owner_profile_updates": [
    {"op": "add", "value": "Owner loves hiking on weekends"},
    {"op": "remove", "find": "Owner likes puzzle games"}
  ]
}
```

- **`add`** (default if `op` is missing): Append a new bullet point. Backward compatible.
- **`replace`**: Find a substring match in the file, replace the entire line containing it with the new value. If no match, fall back to add.
- **`remove`**: Find a substring match and delete the entire line. If no match, skip silently.

### Data model changes

`AgentResult` update fields change from `list[str]` to `list[MemoryUpdate]`, where:

```python
@dataclass(frozen=True)
class MemoryUpdate:
    op: str  # "add", "replace", "remove"
    value: str
    find: str | None = None  # required for replace/remove
```

### Curator changes

`MemoryCurator.apply_updates()` receives `list[MemoryUpdate]` instead of `list[str]`:

- `add`: Same as current behavior (append `- value`, dedup, safety check)
- `replace`: Find line containing `find` substring, replace it with `- value`
- `remove`: Find line containing `find` substring, delete it

All operations still go through safety filtering and length gating.

### Retro-compatibility

The JSON output from the LLM can use either format:
- `["some update"]` → treated as `[{"op": "add", "value": "some update"}]`
- `[{"op": "replace", "find": "...", "value": "..."}]` → parsed as MemoryUpdate

In `RelationshipAgent.respond()`, detect format and normalize to `list[MemoryUpdate]`.

## 3. Conversation History

**Current**: No conversation history. Each LLM call sees only the current message and accumulated state files.

**New**: Maintain a `conversation_history.json` file in the state directory. Store the last N message pairs (owner message + bot reply_text).

### Format

```json
[
  {"role": "owner", "content": "你好", "timestamp": "2026-05-15T13:00:20Z"},
  {"role": "bot", "content": "嘿，你好！很高兴认识你～...", "timestamp": "2026-05-15T13:00:22Z"},
  {"role": "owner", "content": "我喜欢爬山", "timestamp": "2026-05-15T13:01:00Z"},
  {"role": "bot", "content": "爬山好棒！你周末经常去吗？...", "timestamp": "2026-05-15T13:01:03Z"}
]
```

### Display in prompt

The conversation history is injected between the memory snapshot and the current message, formatted as:

```
Recent conversation:
Owner: 你好
Bot: 嘿，你好！很高兴认识你～...
Owner: 我喜欢爬山
Bot: 爬山好棒！你周末经常去吗？...

Current message: 我那个周末去了黄山
Message sent at: 2026-05-15T13:05:00+00:00
```

### Storage and truncation

- `MemoryStore` gains `load_conversation_history()` and `save_conversation_history()` methods
- Max 10 messages (5 conversation turns). When a new message would exceed this, the oldest is evicted.
- History is saved after each bot reply and each proactive message.

### What changes in runtime.py

- After `agent.respond()`, before saving the result, append the owner message and bot reply to conversation history.
- When building the prompt, `PromptBuilder` receives the history from the snapshot.

## 4. Proactive Timing Improvements

**Current problems**:
- `max_idle_seconds=900` (15 min) means the bot stops reaching out after 15 minutes of silence
- Exponential backoff has no cap — after a few ignored proactives, the wait becomes days

**Changes**:

### 4.1 Raise max idle default

Change default `PROACTIVE_MAX_IDLE_SECONDS` from `900` to `86400` (24 hours). The bot can now reach out even after hours of silence, which matches the "later stage: less frequent but still contextual" PRD requirement.

### 4.2 Cap exponential backoff

In `ProactivePolicy.precheck()`, add:

```python
BACKOFF_CAP_SECONDS = 7200  # 2 hours max wait

if seconds_since_proactive < min(backoff_seconds, BACKOFF_CAP_SECONDS):
    return PrecheckDecision(False, ...)
```

### 4.3 Stage-aware minimum idle

In `ProactivePolicy.precheck()`, accept a `stage` parameter:

- `"early"` (identity or profile still default): min_idle = `config.proactive_min_idle_seconds // 2` (more eager)
- Later stages: use the configured `proactive_min_idle_seconds` as-is

The `RelationshipAgent` or `main.py` determines the stage by checking if `snapshot.bot_identity == DEFAULT_BOT_IDENTITY` or `snapshot.owner_profile == DEFAULT_OWNER_PROFILE`, similar to the prompt builder logic.

## 5. What We Are NOT Changing

- Discord adapter (already works well)
- MiniMax client (already works, proxy support added)
- Safety module (already adequate)
- Models other than `AgentResult` and `MemoryUpdate` (minimal disruption)
- `.env` configuration structure (only changing default values for proactive timing)

## 6. File Change Summary

| File | Change |
|---|---|
| `src/bot/agent/prompt_builder.py` | Refactor into layered methods; add history and identity formatting |
| `src/bot/agent/relationship_agent.py` | Parse new memory update format; normalize old format; extract history + identity from snapshot |
| `src/bot/memory/store.py` | Add `load_conversation_history()`, `save_conversation_history()`, default history file; integrate `MemoryUpdate` |
| `src/bot/memory/curator.py` | Handle `MemoryUpdate` with add/replace/remove operations |
| `src/bot/models.py` | Add `MemoryUpdate` dataclass; update `AgentResult` fields to `list[MemoryUpdate]`; add `ConversationEntry` and `ConversationHistory` |
| `src/bot/config.py` | Change default `PROACTIVE_MAX_IDLE_SECONDS` to 86400 |
| `src/bot/runtime.py` | Save owner message + bot reply to conversation history after each turn |
| `src/bot/main.py` | Pass stage info to proactive policy; save proactive messages to history |
| `src/bot/scheduler/proactive.py` | Add backoff cap; accept stage parameter for stage-aware min_idle |
| `tests/` | Update all affected tests |