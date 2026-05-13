import asyncio
import json
from datetime import datetime, timedelta, timezone

from bot.agent import PromptBuilder, RelationshipAgent
from bot.models import MemorySnapshot, ProactiveDecision, RuntimeState
from bot.scheduler import ProactivePlanner, ProactivePolicy, apply_proactive_sent


NOW = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)


def make_state(**overrides) -> RuntimeState:
    values = {
        "last_owner_message_at": NOW - timedelta(seconds=90),
        "last_proactive_sent_at": None,
        "unanswered_proactive_count": 0,
    }
    values.update(overrides)
    return RuntimeState(**values)


def make_snapshot(state: RuntimeState) -> MemorySnapshot:
    return MemorySnapshot(
        bot_identity="Bot identity",
        owner_profile="Owner profile",
        relationship_journal="Relationship journal",
        avatar_prompt="Avatar prompt",
        runtime_state=state,
    )


def test_policy_skips_when_last_owner_message_at_is_none():
    policy = ProactivePolicy(min_idle_seconds=60, max_idle_seconds=300)
    state = make_state(last_owner_message_at=None)

    decision = policy.precheck(state, NOW)

    assert decision.allowed is False
    assert decision.reason == "no_owner_message"


def test_policy_skips_before_min_idle_with_reason_containing_idle():
    policy = ProactivePolicy(min_idle_seconds=60, max_idle_seconds=300)
    state = make_state(last_owner_message_at=NOW - timedelta(seconds=59))

    decision = policy.precheck(state, NOW)

    assert decision.allowed is False
    assert "idle" in decision.reason


def test_policy_allows_inside_idle_window():
    policy = ProactivePolicy(min_idle_seconds=60, max_idle_seconds=300)

    decision = policy.precheck(make_state(), NOW)

    assert decision.allowed is True
    assert decision.reason == ""


def test_policy_handles_naive_persisted_timestamps_as_utc():
    policy = ProactivePolicy(min_idle_seconds=60, max_idle_seconds=300)
    naive_last_owner_message = (NOW - timedelta(seconds=90)).replace(tzinfo=None)
    state = make_state(last_owner_message_at=naive_last_owner_message)

    decision = policy.precheck(state, NOW)

    assert decision.allowed is True


def test_policy_applies_unanswered_backoff_with_reason_containing_backoff():
    policy = ProactivePolicy(min_idle_seconds=60, max_idle_seconds=300)
    state = make_state(
        last_proactive_sent_at=NOW - timedelta(seconds=119),
        unanswered_proactive_count=1,
    )

    decision = policy.precheck(state, NOW)

    assert decision.allowed is False
    assert "backoff" in decision.reason


def test_policy_allows_after_backoff_expires():
    policy = ProactivePolicy(min_idle_seconds=60, max_idle_seconds=300)
    state = make_state(
        last_owner_message_at=NOW - timedelta(seconds=600),
        last_proactive_sent_at=NOW - timedelta(seconds=240),
        unanswered_proactive_count=2,
    )

    decision = policy.precheck(state, NOW)

    assert decision.allowed is True


def test_apply_proactive_sent_updates_runtime_state_fields():
    state = make_state()
    decision = ProactiveDecision(
        should_send=True,
        reason="Owner has been quiet after a meaningful chat.",
        message="Want to talk about yesterday?",
    )

    updated = apply_proactive_sent(state, decision, NOW)

    assert updated is state
    assert updated.last_proactive_sent_at == NOW
    assert updated.last_proactive_reason == decision.reason
    assert updated.last_proactive_message == decision.message
    assert updated.unanswered_proactive_count == 1


class StubAgent:
    def __init__(self, decision: ProactiveDecision) -> None:
        self.decision = decision
        self.calls = 0

    async def plan_proactive(self, snapshot: MemorySnapshot) -> ProactiveDecision:
        self.calls += 1
        return self.decision


def test_planner_returns_precheck_skip_without_calling_agent():
    policy = ProactivePolicy(min_idle_seconds=60, max_idle_seconds=300)
    agent = StubAgent(ProactiveDecision(True, message="Hello"))
    snapshot = make_snapshot(make_state(last_owner_message_at=None))
    planner = ProactivePlanner(policy, agent)

    decision = asyncio.run(planner.maybe_plan(snapshot, NOW))

    assert decision.should_send is False
    assert decision.skip_reason == "no_owner_message"
    assert agent.calls == 0


def test_planner_returns_safe_skip_for_empty_agent_message():
    policy = ProactivePolicy(min_idle_seconds=60, max_idle_seconds=300)
    agent = StubAgent(ProactiveDecision(True, reason="Check in", message="   "))
    snapshot = make_snapshot(make_state())
    planner = ProactivePlanner(policy, agent)

    decision = asyncio.run(planner.maybe_plan(snapshot, NOW))

    assert decision.should_send is False
    assert decision.reason == "Check in"
    assert decision.skip_reason == "empty_proactive_message"


class StubCompletionClient:
    def __init__(self, response: str) -> None:
        self.response = response

    async def complete(self, messages: list[dict[str, str]]) -> str:
        return self.response


def test_planner_with_real_agent_allows_after_backoff_expires():
    policy = ProactivePolicy(min_idle_seconds=60, max_idle_seconds=300)
    state = make_state(
        last_owner_message_at=NOW - timedelta(seconds=600),
        last_proactive_sent_at=NOW - timedelta(seconds=240),
        unanswered_proactive_count=2,
    )
    agent = RelationshipAgent(
        StubCompletionClient(
            json.dumps(
                {
                    "should_send": True,
                    "reason": "after backoff",
                    "message": "Still around if you want to talk.",
                }
            )
        ),
        PromptBuilder("cm6550"),
    )
    planner = ProactivePlanner(policy, agent)

    decision = asyncio.run(planner.maybe_plan(make_snapshot(state), NOW))

    assert decision.should_send is True
    assert decision.reason == "after backoff"
    assert decision.message == "Still around if you want to talk."
