# Architecture

## Overview

The bot is a single-owner Discord companion that learns through conversation and persists state to local files.

```
Discord → DiscordAdapter → BotRuntime → RelationshipAgent → MiniMaxClient
                                ↕                          ↕
                          MemoryStore/Curator        PromptBuilder
```

## Data Flow

### On owner message

1. `DiscordAdapter.on_message()` filters to owner ID + chat channel ID, creates `MessageEvent`
2. `BotRuntime.handle_message()` loads a `MemorySnapshot` from `MemoryStore`
3. `RelationshipAgent.respond()`:
   - **Chat phase**: builds layered prompt → calls LLM → extracts `reply_text`
   - **Reflection phase**: builds analysis prompt → calls LLM → extracts memory updates
4. `BotRuntime` sanitizes reply, sends via Discord, saves conversation history
5. `MemoryCurator.apply_updates()` applies memory changes (add/replace/remove) to markdown files
6. Runtime state updated (last_owner_message_at, reset unanswered_proactive_count)

### On proactive tick

1. `run_proactive_loop()` sleeps for `PROACTIVE_CHECK_SECONDS`, then calls `run_proactive_tick()`
2. `ProactivePlanner.maybe_plan()`:
   - `ProactivePolicy.precheck()` checks idle windows, backoff, and daily limits
   - If allowed, `RelationshipAgent.plan_proactive()` generates a contextual message
3. If message is valid, send via Discord adapter, update runtime state, save to history

## Memory Files

| File | Purpose | Format |
|------|---------|--------|
| `bot_identity.md` | Bot's developing name, personality, voice | Markdown bullets |
| `owner_profile.md` | What the bot knows about the owner | Markdown bullets |
| `relationship_journal.md` | Relationship milestones and tone | Markdown bullets |
| `avatar_prompt.md` | Visual description for avatar generation | Markdown |
| `runtime_state.json` | Conversation counters, proactive state | JSON |
| `conversation_history.json` | Last 10 owner/bot message pairs | JSON array |
| `events.jsonl` | Append-only event log for debugging | JSON lines |

Memory updates support three operations:
- **add** — append a new bullet point (default)
- **replace** — find a line by substring match, replace the entire line
- **remove** — find a line by substring match, delete it

When memory files grow beyond 200 lines, near-duplicate entries are deduplicated via Jaccard word overlap.

## Prompt Design

### Chat prompt (generates reply_text)

System message layers:
1. **Identity** — who the bot is, how to use identity memory
2. **Behavior rules** — conversational style, question limits, language matching
3. **Stage guidance** — dynamic based on conversation count and identity completeness
4. **Output format** — raw JSON `{"reply_text": "..."}`

User message layers:
1. **Memory snapshot** — current state of all 4 markdown files (as data, not instructions)
2. **Conversation history** — last N owner/bot message pairs
3. **Current message** — the owner's latest message + timestamp

### Reflection prompt (generates memory updates)

Analyzes the conversation turn and produces updates for all memory files. Includes onboarding progress checks (has name? has avatar? time to suggest one?).

### Proactive prompt

Lightweight decision prompt: should the bot reach out right now? Must have a specific, warm reason — never generic check-ins.

## Proactive Behavior

**Policy** (`ProactivePolicy`):
- Minimum idle: `PROACTIVE_MIN_IDLE_SECONDS` (or half in early stage)
- Maximum idle: `PROACTIVE_MAX_IDLE_SECONDS` (86400 = 24h by default)
- Backoff: exponential with cap at `PROACTIVE_BACKOFF_CAP_SECONDS` (7200 = 2h)
- Early stage detection: identity not yet formed or owner profile is default

**Valid motivations**: bot name not chosen, follow-up on owner's project, avatar direction, saved follow-up items.

**Invalid**: "Hi", "Are you there?", repeated generic check-ins.

## Failure Handling

| Failure | Behavior |
|---------|----------|
| LLM error | Send fallback reply, do not update memory, log error |
| Invalid JSON | Recover reply_text if possible, fallback otherwise, skip memory updates |
| File write error | Catch OSError, log error, do not crash |
| Discord send error | Log error, no retry loop |
| Ignored proactive | Exponential backoff with cap; stop after repeated ignores |
| Event log failure | Silently skip — best-effort, never blocks the main flow |

## Stages

The bot progresses through stages based on conversation depth:

1. **First meeting** (0-2 exchanges) — warm, present, genuinely curious
2. **Identity forming** (no name yet) — priority: invite the owner to name the bot
3. **Identity forming** (has name) — let personality emerge through responses
4. **Deepening** (6-10 exchanges) — reference past naturally, make owner feel remembered
5. **Established** (10+ exchanges) — rich shared history, rarely need to ask questions
