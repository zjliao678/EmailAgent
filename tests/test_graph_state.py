"""Tests for email_agent.graph.state — GraphState definition (TDD)."""

from email_agent.graph.state import GraphState, Intent, RiskLevel


class TestGraphState:
    def test_default_state_has_empty_intents(self):
        state = GraphState(
            email_id="id-1",
            message_id="<msg@example.com>",
            sender="a@example.com",
            subject="Hello",
            body="<email_content>Hello</email_content>",
        )
        assert state.intents == []

    def test_default_risk_level_is_none(self):
        state = GraphState(
            email_id="id-1",
            message_id="<msg@example.com>",
            sender="a@example.com",
            subject="Hello",
            body="<email_content>Hello</email_content>",
        )
        assert state.risk_level is None

    def test_injection_detected_defaults_to_false(self):
        state = GraphState(
            email_id="id-1",
            message_id="<msg@example.com>",
            sender="a@example.com",
            subject="Hello",
            body="<email_content>Hello</email_content>",
        )
        assert state.injection_detected is False

    def test_state_is_immutable_via_copy(self):
        """GraphState updates must return new instances (LangGraph pattern)."""
        state = GraphState(
            email_id="id-1",
            message_id="<msg@example.com>",
            sender="a@example.com",
            subject="Hello",
            body="<email_content>Hello</email_content>",
        )
        updated = state.model_copy(update={"subject": "Updated"})
        assert updated.subject == "Updated"
        assert state.subject == "Hello"  # original unchanged


class TestIntent:
    def test_intent_has_name_and_entities(self):
        intent = Intent(name="reply", entities={"to": "user@example.com"}, reason="User asked")
        assert intent.name == "reply"
        assert intent.entities["to"] == "user@example.com"

    def test_intent_risk_defaults_to_none(self):
        intent = Intent(name="label", entities={}, reason="")
        assert intent.risk_level is None


class TestRiskLevel:
    def test_ordering(self):
        assert RiskLevel.LOW < RiskLevel.MEDIUM < RiskLevel.HIGH
