from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from bot.models import MemorySnapshot, ProactiveDecision, RuntimeState


@dataclass(frozen=True)
class PrecheckDecision:
    allowed: bool
    reason: str = ""


class ProactiveAgent(Protocol):
    async def plan_proactive(self, snapshot: MemorySnapshot) -> ProactiveDecision: ...


class ProactivePolicy:
    def __init__(self, min_idle_seconds: int, max_idle_seconds: int) -> None:
        self.min_idle_seconds = min_idle_seconds
        self.max_idle_seconds = max_idle_seconds

    def precheck(self, state: RuntimeState, now: datetime) -> PrecheckDecision:
        if state.last_owner_message_at is None:
            return PrecheckDecision(False, "no_owner_message")

        idle_seconds = (now - state.last_owner_message_at).total_seconds()
        if idle_seconds < self.min_idle_seconds:
            return PrecheckDecision(
                False,
                f"idle {idle_seconds:.0f}s below minimum {self.min_idle_seconds}s",
            )

        if (
            state.unanswered_proactive_count > 0
            and state.last_proactive_sent_at is not None
        ):
            backoff_seconds = self.min_idle_seconds * (
                2**state.unanswered_proactive_count
            )
            seconds_since_proactive = (
                now - state.last_proactive_sent_at
            ).total_seconds()
            if seconds_since_proactive < backoff_seconds:
                return PrecheckDecision(
                    False,
                    f"backoff {seconds_since_proactive:.0f}s below {backoff_seconds}s",
                )

        return PrecheckDecision(True)


def apply_proactive_sent(
    state: RuntimeState, decision: ProactiveDecision, now: datetime
) -> RuntimeState:
    state.last_proactive_sent_at = now
    state.last_proactive_reason = decision.reason
    state.last_proactive_message = decision.message
    state.unanswered_proactive_count += 1
    return state


class ProactivePlanner:
    def __init__(self, policy: ProactivePolicy, agent: ProactiveAgent) -> None:
        self._policy = policy
        self._agent = agent

    async def maybe_plan(
        self, snapshot: MemorySnapshot, now: datetime
    ) -> ProactiveDecision:
        precheck = self._policy.precheck(snapshot.runtime_state, now)
        if not precheck.allowed:
            return ProactiveDecision(False, skip_reason=precheck.reason)

        decision = await self._agent.plan_proactive(snapshot)
        if decision.should_send and not decision.message.strip():
            return ProactiveDecision(
                False,
                reason=decision.reason,
                skip_reason="empty_proactive_message",
            )

        return decision
