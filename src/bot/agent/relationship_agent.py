from __future__ import annotations

import json
from typing import Any, Protocol

from bot.agent.prompt_builder import PromptBuilder
from bot.models import AgentResult, MemorySnapshot, MessageEvent, ProactiveDecision
from bot.safety import sanitize_discord_output


FALLBACK_REPLY = "I'm here with you. Tell me a little more?"


class CompletionClient(Protocol):
    async def complete(self, messages: list[dict[str, str]]) -> str: ...


class RelationshipAgent:
    def __init__(self, client: CompletionClient, prompt_builder: PromptBuilder) -> None:
        self._client = client
        self._prompt_builder = prompt_builder

    async def respond(
        self, snapshot: MemorySnapshot, event: MessageEvent
    ) -> AgentResult:
        messages = self._prompt_builder.build_chat_messages(snapshot, event)
        raw_text = await self._client.complete(messages)

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            return AgentResult(reply_text=sanitize_discord_output(raw_text))

        if not isinstance(parsed, dict):
            return AgentResult(reply_text=sanitize_discord_output(raw_text))

        reply_text = parsed.get("reply_text")
        if not isinstance(reply_text, str) or not reply_text.strip():
            reply_text = FALLBACK_REPLY

        return AgentResult(
            reply_text=sanitize_discord_output(reply_text),
            bot_identity_updates=self._string_list(
                parsed.get("bot_identity_updates")
            ),
            owner_profile_updates=self._string_list(
                parsed.get("owner_profile_updates")
            ),
            relationship_journal_updates=self._string_list(
                parsed.get("relationship_journal_updates")
            ),
            avatar_updates=self._string_list(parsed.get("avatar_updates")),
            runtime_notes=self._string_list(parsed.get("runtime_notes")),
        )

    async def plan_proactive(self, snapshot: MemorySnapshot) -> ProactiveDecision:
        if snapshot.runtime_state.unanswered_proactive_count > 0:
            return ProactiveDecision(
                should_send=False,
                skip_reason="waiting_for_owner_response",
            )

        return ProactiveDecision(
            should_send=False,
            skip_reason="proactive_planning_not_implemented",
        )

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]
