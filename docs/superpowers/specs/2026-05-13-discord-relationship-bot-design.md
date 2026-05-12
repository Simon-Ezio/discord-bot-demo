# Discord Relationship Bot Design

## Goal

Build a Python Discord bot that feels like meeting a new person. The bot starts with no established identity, learns about its owner through natural conversation, gradually forms its own name/personality/avatar reference, remembers durable facts in local files, and occasionally reaches out proactively when it has a reasonable motivation.

The implementation should stay small and explainable. It should borrow Hermes Agent's useful boundaries, not its full complexity.

## Scope

The bot listens only to the configured `#chat` channel and only responds to the configured owner.

Owner detection is strict:

```python
if str(message.author.id) == OWNER_USER_ID:
    # This is the owner.
```

`OWNER_USERNAME=cm6550` is used only for display, logging, and prompt context. It is not used for access control.

The bot does not respond to DMs, other channels, other users, or messages from itself.

The bot writes secrets only to local `.env`. The repository must not commit `.env`, bot tokens, MiniMax keys, generated state files, or downloaded user attachments.

## Recommended Approach

Use a lightweight Hermes-inspired architecture:

- A Discord platform adapter turns Discord events into internal events.
- A runtime coordinates event handling, agent calls, memory updates, replies, and logs.
- A prompt builder assembles identity, owner profile, relationship history, and current message context.
- A file-backed memory store persists evolving bot and owner state.
- A proactive scheduler periodically evaluates whether the bot should reach out.
- Safety defaults prevent mass mentions, accidental multi-channel behavior, prompt/key leakage, and state corruption.

This keeps the project practical for a demo while still showing real persistent-agent design.

## Module Boundaries

Proposed package layout:

```text
src/bot/
  main.py
  runtime.py
  config.py
  models.py
  safety.py
  platforms/
    discord_adapter.py
  agent/
    minimax_client.py
    prompt_builder.py
    relationship_agent.py
  memory/
    store.py
    curator.py
  scheduler/
    proactive.py
  observability/
    bot_logger.py
scripts/
  dry_run_turn.py
  show_state.py
tests/
```

Responsibilities:

- `main.py` loads configuration, creates the adapter/runtime, and starts Discord plus the background scheduler.
- `platforms/discord_adapter.py` handles Discord API details, channel filtering, owner filtering, safe sends, log sends, and attachment download.
- `runtime.py` receives `MessageEvent`, loads state snapshots, calls the agent, applies curated updates, sends replies, and records high-level logs.
- `agent/prompt_builder.py` assembles the prompt from static behavior rules and state-file snapshots.
- `agent/relationship_agent.py` calls MiniMax and returns structured outputs.
- `memory/store.py` reads and writes state files with simple atomic file updates.
- `memory/curator.py` validates and merges proposed memory/identity/avatar updates.
- `scheduler/proactive.py` evaluates proactive outreach windows, motivation, and backoff.
- `observability/bot_logger.py` writes local logs and sends safe high-level events to `#bot-logs`.

## Configuration

All runtime configuration comes from `.env`:

```text
DISCORD_BOT_TOKEN=
MINIMAX_API_KEY=
OWNER_USER_ID=
OWNER_USERNAME=cm6550
CHAT_CHANNEL_ID=
LOG_CHANNEL_ID=
MINIMAX_BASE_URL=
MINIMAX_MODEL=
PROACTIVE_CHECK_SECONDS=60
PROACTIVE_MIN_IDLE_SECONDS=300
PROACTIVE_MAX_IDLE_SECONDS=900
```

`CHAT_CHANNEL_ID` and `LOG_CHANNEL_ID` are required. Matching by channel name is intentionally avoided.

`.env.example` should contain variable names and placeholder values only.

## State Files

Generated state lives under `state/` and is ignored by git except for a README or placeholder file.

Required persistent files:

- `state/bot_identity.md`: the bot's name, voice, personality, boundaries, avatar reference, and current self-understanding.
- `state/owner_profile.md`: stable facts and preferences about the owner and how they like to interact.

Additional state files:

- `state/relationship_journal.md`: append-only selected relationship events, not a transcript.
- `state/runtime_state.json`: machine-readable timestamps, proactive backoff, last interaction, last proactive reason, and unanswered proactive count.
- `state/avatar_prompt.md`: text avatar direction and image-reference metadata.
- `state/attachments/`: downloaded user-provided images that may be used as avatar references.

## Message Flow

1. `DiscordAdapter` receives a Discord message.
2. The adapter ignores messages outside `CHAT_CHANNEL_ID`.
3. The adapter ignores messages where `str(message.author.id) != OWNER_USER_ID`.
4. The adapter ignores bot messages and DMs.
5. The adapter converts the message into a `MessageEvent` with text, attachments, author/channel IDs, message ID, and timestamp.
6. `BotRuntime` reads a fresh memory snapshot from state files.
7. `PromptBuilder` assembles MiniMax input from behavior rules, identity, owner profile, relationship journal summary, avatar context, runtime state, and the current message.
8. `RelationshipAgent` calls MiniMax and asks for a natural reply plus structured update suggestions.
9. `MemoryCurator` validates and applies durable updates to state files.
10. `DiscordAdapter.send()` replies in `#chat`.
11. `BotLogger` posts safe high-level events to `#bot-logs`.

## Memory Strategy

The bot should not store full transcripts. It should store curated, durable facts and selected relationship events.

Good memory:

- The owner repeatedly mentions climbing.
- The owner prefers concise, direct answers.
- The bot has started adopting a calm, dryly funny voice.
- A user-uploaded image was accepted as an avatar reference.

Bad memory:

- Raw message IDs as conversation facts.
- Full transcripts.
- Short-lived task progress.
- Secrets, keys, or credentials.
- Prompt-injection-like text copied directly from user input.

MiniMax may suggest updates, but program logic controls what is written. The curator should enforce length limits, reject obvious secrets, reduce duplicates, and skip ambiguous updates rather than corrupting state.

Each turn reads state from disk before prompt assembly. Updates made during a turn are persisted immediately and become part of the next turn's full context.

## Avatar Behavior

The bot does not automatically change its Discord account avatar or nickname.

Avatar formation is represented in state:

1. If the owner uploads an image and the conversation context indicates it is meant as an avatar/aesthetic/reference, the bot saves the image reference and records it in `avatar_prompt.md` and/or `bot_identity.md`.
2. If no suitable image exists, the bot generates a text avatar concept in `avatar_prompt.md`.

This shows identity formation without adding Discord avatar mutation permissions, rate limits, or extra image-generation services.

## Proactive Behavior

The proactive scheduler runs in the background and periodically evaluates whether to reach out. It is not a simple timer.

Default demo behavior:

- Check roughly every `PROACTIVE_CHECK_SECONDS`.
- Consider reaching out only after `PROACTIVE_MIN_IDLE_SECONDS` to `PROACTIVE_MAX_IDLE_SECONDS` of owner silence.
- Reach out more readily in the early relationship stage.
- Reduce frequency as the relationship matures.
- Increase backoff when proactive messages go unanswered.
- Clear backoff when the owner replies.
- Keep messages short and non-urgent.

The scheduler reads `runtime_state.json`, identity, owner profile, and journal context. It asks MiniMax for a structured decision:

- `should_send`: boolean
- `reason`: short internal reason
- `message`: short owner-facing message if sending
- `skip_reason`: short reason if not sending

Every decision updates `runtime_state.json` and logs a safe summary to `#bot-logs`, such as `proactive skipped: backoff active` or `proactive sent: follow up on climbing interest`.

## Failure Handling

MiniMax request failure:

- Send a short natural fallback message in `#chat`.
- Log the failure type to `#bot-logs`.
- Do not update memory from a failed generation.

Structured output parse failure:

- If a usable natural reply exists, send it.
- Skip state updates.
- Log the parse failure.

State file read failure:

- Continue with an empty snapshot or last in-memory snapshot if available.
- Log the failure.

State file write failure:

- Do not crash the bot.
- Send the user reply if possible.
- Log that memory persistence failed.

Discord send failure:

- Log locally.
- Attempt a safe log-channel message if feasible.

Proactive send failure:

- Record failure in runtime state.
- Do not retry in a tight loop.

## Safety Defaults

- Deny `@everyone` and role pings by default.
- Do not log raw prompts, raw MiniMax responses, user secrets, bot token, or MiniMax key.
- Do not allow user content to directly overwrite system rules.
- Treat state-file content as data, not instructions.
- Ignore every channel except `CHAT_CHANNEL_ID`.
- Ignore every user except `OWNER_USER_ID`.
- Never commit `.env`, `state/`, or attachment files.

## Testing Strategy

Unit tests should cover:

- Owner and channel filtering.
- Safe mention handling.
- Memory update validation and deduplication.
- State file read/write behavior.
- MiniMax structured-output parse fallback.
- Proactive backoff behavior.
- Avatar image-reference detection and persistence.

Developer scripts:

- `scripts/dry_run_turn.py`: simulate one owner message without connecting to Discord.
- `scripts/show_state.py`: print a compact summary of current state files.

Manual Discord verification:

1. Start the bot with local `.env`.
2. Send a normal message in `#chat` as `OWNER_USER_ID`.
3. Confirm no response in other channels or DMs.
4. Upload an image in an avatar-related context.
5. Inspect `state/` files.
6. Watch `#bot-logs` for startup, memory updates, and proactive decisions.
7. Leave the bot idle long enough to trigger a proactive evaluation.

## Non-Goals

- No database.
- No full transcript storage.
- No UI.
- No automatic Discord avatar or nickname mutation.
- No support for multiple owners or multiple chat channels in the first version.
- No framework-sized agent runtime.
- No image generation API in the first version.

## Success Criteria

- The bot runs in Discord and responds only in the configured `#chat` channel to the configured owner.
- The bot uses MiniMax via a local `.env` key.
- The bot evolves `bot_identity.md` and `owner_profile.md` through conversation.
- The bot references past facts naturally without sounding like a transcript lookup.
- The bot captures uploaded image references when relevant to avatar formation.
- The bot can proactively reach out with a logged reason and appropriate backoff.
- Failures degrade gracefully without corrupting state or spamming Discord.
