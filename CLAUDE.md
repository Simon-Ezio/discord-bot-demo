# Project: Hermes-lite Discord Relationship Bot

## Goal

Build a minimal Discord bot that starts with no fixed identity and develops through conversation with its owner. It persists bot identity and owner/relationship memory to local files, reads those files back into context on each response, and occasionally reaches out proactively with a reason.

## Non-goals

- No database.
- No vector store.
- No complex plugin architecture.
- No full transcript storage.
- No over-engineering.

## Tech stack

- Python 3.11+
- discord.py
- httpx
- python-dotenv
- uv / pyproject.toml
- local markdown/json files for state

## Project structure

```
run.py               # entry point
src/bot/
  config.py           # BotConfig from env
  main.py             # build_runtime, amain, proactive loop
  runtime.py          # BotRuntime orchestrator
  models.py           # MemorySnapshot, AgentResult, MemoryUpdate, etc.
  safety.py           # output sanitization, memory content filtering
  agent/
    prompt_builder.py # layered prompt assembly
    relationship_agent.py  # chat + reflection + proactive agent
    minimax_client.py # LLM adapter
  memory/
    store.py          # file I/O, snapshots, history
    curator.py        # memory update operations (add/replace/remove)
  platforms/
    discord_adapter.py  # Discord I/O
  scheduler/
    proactive.py      # proactive timing and planning
  observability/
    bot_logger.py     # console + Discord log channel
tests/
scripts/
  dry_run_turn.py     # offline turn testing
  show_state.py       # inspect state files
```

## Important behavior

- The bot should feel like meeting a person, not filling out a survey.
- Ask at most one natural question at a time.
- Do not interrogate the owner.
- Remember only stable, useful information.
- Reference memory naturally, not mechanically.
- Proactive messages must have a clear reason.
- If ignored, back off.
- If LLM fails, send a gentle fallback and do not update memory.

## State files

- `state/bot_identity.md` — bot's developing identity
- `state/owner_profile.md` — what the bot knows about the owner
- `state/relationship_journal.md` — relationship milestones
- `state/avatar_prompt.md` — avatar description
- `state/runtime_state.json` — conversation and proactive counters
- `state/conversation_history.json` — last 10 messages
- `state/events.jsonl` — append-only event log

## Coding style

- Simple functions over classes unless classes clearly help.
- Small modules.
- Clear names.
- Defensive error handling.
- No hidden magic.
- No secrets in source code.

## Development rules

- Make one coherent change at a time.
- After each change, run `uv run pytest` and `uv run python -m py_compile` on changed files.
- Do not rewrite unrelated code.
- Do not introduce large dependencies without asking.

## Run

```bash
uv sync --extra dev
cp .env.example .env
uv run python run.py
```
