# Discord Relationship Bot

A single-owner Discord bot that keeps local memory in markdown/JSON files, replies in one configured channel, and can send simple proactive check-ins.

## Setup

```bash
uv sync --extra dev
cp .env.example .env  # if you keep an example locally
```

Create `.env` in the repo root:

```dotenv
DISCORD_BOT_TOKEN=your-discord-bot-token
MINIMAX_API_KEY=your-minimax-api-key
OWNER_USER_ID=your-discord-user-id
OWNER_USERNAME=your-display-name
CHAT_CHANNEL_ID=channel-for-chat
LOG_CHANNEL_ID=channel-for-runtime-logs
STATE_DIR=state
PROACTIVE_CHECK_SECONDS=60
PROACTIVE_MIN_IDLE_SECONDS=300
PROACTIVE_MAX_IDLE_SECONDS=86400
PROACTIVE_EARLY_IDLE_SECONDS=150
PROACTIVE_BACKOFF_CAP_SECONDS=7200
MINIMAX_MODEL=MiniMax-Text-01
```

`MINIMAX_BASE_URL` is optional and defaults to the MiniMax chat completion URL.

## Proactive Debug Timing

For fast local proactive testing:

```dotenv
PROACTIVE_CHECK_SECONDS=10
PROACTIVE_MIN_IDLE_SECONDS=30
PROACTIVE_MAX_IDLE_SECONDS=86400
PROACTIVE_EARLY_IDLE_SECONDS=15
PROACTIVE_BACKOFF_CAP_SECONDS=60
```

`PROACTIVE_CHECK_SECONDS` controls how often the loop wakes up. `PROACTIVE_MIN_IDLE_SECONDS` controls normal idle delay. `PROACTIVE_EARLY_IDLE_SECONDS` makes the first-meeting stage easier to test. `PROACTIVE_BACKOFF_CAP_SECONDS` prevents ignored proactive messages from backing off for hours during development.

## Discord IDs

Enable Developer Mode in Discord:

1. Open Discord settings.
2. Go to Advanced.
3. Turn on Developer Mode.
4. Right-click your user and copy ID for `OWNER_USER_ID`.
5. Right-click the chat channel and copy ID for `CHAT_CHANNEL_ID`.
6. Right-click the log channel and copy ID for `LOG_CHANNEL_ID`.

The bot also needs Message Content Intent enabled in the Discord Developer Portal for the bot application.

## Run

```bash
uv run python -m bot.main
```

Inspect local state without printing secrets:

```bash
uv run python scripts/show_state.py --state-dir state
```

Run a safe local dry turn. This always uses a deterministic console dry-run agent by default, even when `.env` contains `MINIMAX_API_KEY`:

```bash
uv run python scripts/dry_run_turn.py --message "hello" --state-dir state
```

To explicitly test the real MiniMax path from the dry-run script, pass `--use-minimax`:

```bash
uv run python scripts/dry_run_turn.py --message "hello" --state-dir state --use-minimax
```

## Architecture

- Memory files: `bot_identity.md`, `owner_profile.md`, `relationship_journal.md`, `avatar_prompt.md`
- Recent history: `conversation_history.json`, capped to the last 10 messages
- Proactive runtime: `runtime_state.json`
- Prompt design: layered identity, behavior rules, stage guidance, memory snapshot, recent history, current message
- Failure handling: invalid LLM JSON falls back to sanitized text or a short fallback reply

## Manual Verification

1. Confirm `.env` contains the Discord token, MiniMax key, owner ID, chat channel ID, and log channel ID.
2. Run `uv run python scripts/show_state.py --state-dir state` and confirm the state sections render.
3. Run `uv run python scripts/dry_run_turn.py --message "test" --state-dir state` and confirm a deterministic console reply appears.
4. Start the bot with `uv run python -m bot.main`.
5. Send a message from `OWNER_USER_ID` in `CHAT_CHANNEL_ID`.
6. Confirm the bot replies in the chat channel and runtime logs appear in `LOG_CHANNEL_ID`.
7. Confirm messages from other users, DMs, and other channels are ignored.

`.env` and `state/` contain local secrets or personal state and are intentionally not committed.
