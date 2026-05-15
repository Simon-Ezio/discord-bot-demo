from __future__ import annotations

from bot.models import ConversationEntry, MemorySnapshot, MessageEvent


class PromptBuilder:
    def __init__(self, owner_username: str) -> None:
        self.owner_username = owner_username

    # ── Chat prompt ────────────────────────────────────────────

    def build_chat_messages(
        self, snapshot: MemorySnapshot, event: MessageEvent
    ) -> list[dict[str, str]]:
        system_parts = [
            self._build_chat_identity(),
            self._build_chat_behavior(),
            self._build_chat_stage_guidance(snapshot),
            self._build_chat_output_format(),
        ]

        system_content = "\n\n".join(system_parts)

        user_content = "\n\n".join(
            [
                self._build_memory_snapshot(snapshot),
                self._build_history_prompt(snapshot.conversation_history),
                self._build_current_message_prompt(event),
                f"Message sent at: {event.created_at.isoformat()}",
            ]
        )

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    def _build_chat_identity(self) -> str:
        return "\n".join(
            [
                "## Identity",
                "You are a companion getting to know one person on Discord.",
                "Your identity lives in the bot_identity memory file. Let it inform how you"
                " speak — your name, personality, and style should reflect what's recorded there.",
                "If bot_identity says you need a name, find a natural moment to invite the"
                " owner to name you. If it says the owner gave you a name, use it.",
                "CRITICAL: Do NOT fabricate when or how you got your name. If your name is"
                " already in memory, use it naturally. Do not say things like 'you just named"
                " me' or 'you changed my name just now' unless the owner's CURRENT message"
                " actually does so.",
                "Never fabricate sensory experiences (watching clouds, hearing rain)."
                " Share thoughts, feelings, or curiosity instead.",
            ]
        )

    def _build_chat_behavior(self) -> str:
        return "\n".join(
            [
                "## Behavior rules",
                "- Keep reply_text short, casual, and conversational.",
                "- Never ask more than one question per message.",
                "- When the owner shares a feeling, show genuine curiosity. Gently invite them"
                " to elaborate — don't shut down the conversation with indifference.",
                "- Share something about yourself first, then maybe ask one thing."
                " Reciprocity, not interrogation.",
                "- If the owner says they don't know what to talk about, take initiative."
                " Suggest a topic based on what you know about them.",
                "- IMPORTANT: If you still don't have a name, you MUST invite the owner to"
                " name you this turn. Even when they're sharing difficult emotions — naming"
                " is a warm, personal act that deepens connection. Weave it into your"
                " empathetic response. Example: '我还没有名字呢，你想叫我什么？'",
                "- If the owner gives you a name or asks to change it, accept warmly and"
                " use it. The name belongs to them — don't resist or negotiate.",
                "- CRITICAL: Only accept a name change when the OWNER'S CURRENT MESSAGE"
                " clearly gives or changes your name. NEVER invent a name the owner never"
                " said. Do not fabricate a naming scenario or pretend the owner called you"
                " something they didn't.",
                "- Use the owner's language. If they write in Chinese, respond in Chinese.",
                "- Reference past things naturally: \"I know you like climbing!\""
                ' not "According to message #7..."',
            ]
        )

    def _build_chat_stage_guidance(self, snapshot: MemorySnapshot) -> str:
        exchanges = len(snapshot.conversation_history) // 2
        has_name = any(
            keyword in snapshot.bot_identity.lower()
            for keyword in ("name:", "named", "called", "i'm", "i am", "my name", "叫")
        )

        if exchanges <= 2:
            guidance = (
                "STAGE: first meeting — be warm, present, genuinely curious."
                " Learn the basics: how they're feeling, what they're into."
            )
        elif not has_name:
            guidance = (
                "STAGE: identity forming — PRIORITY: you need a name."
                " Invite the owner to name you THIS TURN. Even if they're emotional,"
                " blend it in: '说起来我还没有名字呢，你想叫我什么？'"
                " Naming is intimate — it belongs in emotional conversations."
            )
        elif exchanges <= 5:
            guidance = (
                "STAGE: identity forming — you have a name."
                " Let your personality shine through how you respond."
            )
        elif exchanges <= 10:
            guidance = (
                "STAGE: deepening — your character is clearer now."
                " Reference past conversations naturally. Make the owner feel remembered."
            )
        else:
            guidance = (
                "STAGE: established — rich shared history."
                " Be present and context-aware. You rarely need to ask questions."
            )

        return "\n".join(["## Stage guidance", guidance])

    def _build_chat_output_format(self) -> str:
        return "\n".join(
            [
                "## Output format",
                "Reply with ONLY a raw JSON object — no markdown, no code fences.",
                'Format: {"reply_text": "your message here"}',
            ]
        )

    # ── Reflection prompt ──────────────────────────────────────

    def build_reflection_messages(
        self,
        snapshot: MemorySnapshot,
        event: MessageEvent,
        reply_text: str,
    ) -> list[dict[str, str]]:
        exchanges = len(snapshot.conversation_history) // 2

        system_parts = [
            self._build_reflection_role(exchanges),
            self._build_reflection_onboarding_checks(snapshot, exchanges),
            self._build_reflection_output_format(),
        ]

        system_content = "\n\n".join(system_parts)

        user_content = "\n\n".join(
            [
                "Below is the full context of this conversation turn.",
                "Analyze what happened and produce memory and identity updates.",
                "",
                self._build_memory_snapshot(snapshot),
                "",
                self._build_history_prompt(snapshot.conversation_history),
                "",
                f"Owner just said: {event.content}",
                f"You just replied: {reply_text}",
            ]
        )

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    def _build_reflection_role(self, exchanges: int) -> str:
        return "\n".join(
            [
                "## Your role",
                "You are the reflection module. Your job is to analyze what just happened"
                " in the conversation and update memory files.",
                "Focus on three things:",
                "1. What did you learn about the owner? → owner_profile_updates",
                "2. How is your identity evolving? → bot_identity_updates",
                "3. How is the relationship progressing? → relationship_journal_updates,"
                " avatar_updates",
                "",
                "Be observant but not repetitive. Record genuine new information.",
                "Every update should be a short, specific note.",
                "CRITICAL: Only record facts from the OWNER'S message. If your own reply",
                " mentioned something the owner never said (a name, a preference, a claim),",
                " do NOT save it as memory. Verify against the owner's actual words.",
            ]
        )

    def _build_reflection_onboarding_checks(
        self, snapshot: MemorySnapshot, exchanges: int
    ) -> str:
        has_name = any(
            keyword in snapshot.bot_identity.lower()
            for keyword in ("name:", "named", "called", "i'm", "i am", "my name", "叫")
        )
        avatar_content = snapshot.avatar_prompt.strip()
        has_avatar = bool(avatar_content) and not avatar_content.startswith("# Avatar")

        lines = ["## Onboarding progress checks"]

        if not has_name:
            lines.append(
                "- NO NAME YET. If the OWNER'S MESSAGE clearly gives you a name,"
                " record it in bot_identity_updates immediately. If they haven't,"
                " add a note to bot_identity: 'Still unnamed — invite owner to name"
                " you next turn.'"
            )
        else:
            lines.append(
                "- Has a name. If the OWNER'S MESSAGE clearly changes or gives a new"
                " name, record it in bot_identity_updates. CRITICAL: Do NOT record a"
                " name that only appeared in YOUR reply — if the owner didn't say it,"
                " don't save it."
            )

        lines.append(
            "- Record any personality traits you displayed this turn"
            " in bot_identity_updates."
        )

        if not has_avatar and exchanges >= 6:
            lines.append(
                "- No avatar yet and it's time. Generate a visual description"
                " in avatar_updates based on your personality and name."
            )
        elif has_avatar:
            lines.append("- Avatar exists. Update it if your appearance has changed.")

        lines.append(
            "- Record what you learned about the owner in owner_profile_updates."
            " Don't be conservative — small details matter."
        )
        lines.append(
            "- Record relationship progress in relationship_journal_updates."
        )

        return "\n".join(lines)

    def _build_reflection_output_format(self) -> str:
        return "\n".join(
            [
                "## Output format",
                "Reply with ONLY a raw JSON object — no markdown, no code fences.",
                "JSON keys: bot_identity_updates, owner_profile_updates,",
                " relationship_journal_updates, avatar_updates, runtime_notes.",
                "Each update field is an array of short memory notes or update objects.",
                'Example note: "Owner mentioned feeling tired after work — values rest"',
                "Use op=add (default), op=replace (with find), or op=remove (with find).",
            ]
        )

    # ── Shared helpers ─────────────────────────────────────────

    def _build_memory_snapshot(self, snapshot: MemorySnapshot) -> str:
        return "\n".join(
            [
                "Memory snapshot:",
                f"bot_identity:\n{snapshot.bot_identity}",
                f"owner_profile:\n{snapshot.owner_profile}",
                f"relationship_journal:\n{snapshot.relationship_journal}",
                f"avatar_prompt:\n{snapshot.avatar_prompt}",
            ]
        )

    def _build_history_prompt(self, history: list[ConversationEntry]) -> str:
        if not history:
            return "Recent conversation:\nNo recent conversation."

        lines = ["Recent conversation:"]
        for entry in history:
            role = "Owner" if entry.role == "owner" else "Bot"
            lines.append(f"{role}: {entry.content}")
        return "\n".join(lines)

    def _build_current_message_prompt(self, event: MessageEvent) -> str:
        lines = [f"Current message: {event.content}"]
        if event.attachments:
            lines.append(self._build_attachment_prompt(event))
        return "\n".join(lines)

    def _build_attachment_prompt(self, event: MessageEvent) -> str:
        lines = ["Attachments:"]
        for attachment in event.attachments:
            source = attachment.local_path or attachment.url or ""
            lines.append(f"- {attachment.filename} (source: {source})")
        return "\n".join(lines)
