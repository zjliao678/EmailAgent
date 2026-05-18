"""Tests for Phase 4 memory modules — written before implementation (TDD)."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from email_agent.memory.short_term import ThreadMemory
from email_agent.memory.long_term import VectorMemory, MemoryRecord
from email_agent.memory.preferences import UserPreferences, PreferenceRule


# ── ThreadMemory (short-term) ─────────────────────────────────────────────────


class TestThreadMemory:
    def test_add_and_retrieve_messages(self):
        mem = ThreadMemory()
        mem.add(thread_id="t1", role="user", content="Hello")
        mem.add(thread_id="t1", role="assistant", content="Hi there")
        history = mem.get(thread_id="t1")
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_different_threads_are_isolated(self):
        mem = ThreadMemory()
        mem.add(thread_id="t1", role="user", content="Thread 1")
        mem.add(thread_id="t2", role="user", content="Thread 2")
        assert len(mem.get("t1")) == 1
        assert len(mem.get("t2")) == 1

    def test_empty_thread_returns_empty_list(self):
        mem = ThreadMemory()
        assert mem.get("unknown-thread") == []

    def test_get_within_token_limit(self):
        """Messages within 8K token limit are returned as-is."""
        mem = ThreadMemory(max_tokens=8000)
        for i in range(5):
            mem.add("t1", "user", f"Short message {i}")
        history = mem.get("t1")
        assert len(history) == 5

    def test_exceeds_token_limit_triggers_summarization(self):
        """When token count exceeds limit, a summarizer is called."""
        mock_summarizer = MagicMock(return_value="Summary of previous messages")
        mem = ThreadMemory(max_tokens=50, summarizer=mock_summarizer)
        # Add messages that will exceed the token limit
        for i in range(20):
            mem.add("t1", "user", "This is a longer message that uses many tokens " * 2)
        mem.get("t1")
        mock_summarizer.assert_called()

    def test_clear_thread(self):
        mem = ThreadMemory()
        mem.add("t1", "user", "Hello")
        mem.clear("t1")
        assert mem.get("t1") == []


# ── VectorMemory (long-term) ──────────────────────────────────────────────────


@pytest.fixture
def vector_mem():
    """In-memory ChromaDB instance for tests."""
    import chromadb
    client = chromadb.Client()  # ephemeral (in-memory)
    return VectorMemory(client=client)


class TestVectorMemory:
    def test_store_and_retrieve(self, vector_mem):
        record = MemoryRecord(
            id="rec-1",
            email_id="email-1",
            sender="alice@example.com",
            summary="Alice asked about the Q2 report",
            created_at=datetime.now(timezone.utc),
        )
        vector_mem.store(record)
        results = vector_mem.search("Q2 report", top_k=3)
        assert len(results) >= 1
        assert any("Q2" in r.summary for r in results)

    def test_search_returns_relevant_results(self, vector_mem):
        records = [
            MemoryRecord("r1", "e1", "alice@e.com", "Meeting about budget planning", datetime.now(timezone.utc)),
            MemoryRecord("r2", "e2", "bob@e.com", "Holiday party invitation", datetime.now(timezone.utc)),
        ]
        for r in records:
            vector_mem.store(r)
        results = vector_mem.search("budget", top_k=1)
        assert results[0].summary == "Meeting about budget planning"

    def test_delete_by_sender_removes_all_records(self, vector_mem):
        """Right-to-be-forgotten: delete all records for a sender."""
        for i in range(3):
            vector_mem.store(MemoryRecord(
                f"r{i}", f"e{i}", "target@evil.com",
                f"Message {i} content",
                datetime.now(timezone.utc),
            ))
        vector_mem.store(MemoryRecord(
            "r-other", "e-other", "other@example.com",
            "Unrelated message", datetime.now(timezone.utc),
        ))
        vector_mem.delete_by_sender("target@evil.com")
        results = vector_mem.search("Message content", top_k=10)
        assert all(r.sender != "target@evil.com" for r in results)

    def test_expired_records_not_returned(self, vector_mem):
        """Records older than 90 days should not appear in results."""
        old_date = datetime.now(timezone.utc) - timedelta(days=91)
        vector_mem.store(MemoryRecord(
            "old-rec", "e-old", "old@example.com",
            "Very old message content",
            created_at=old_date,
        ))
        results = vector_mem.search("Very old message", top_k=10)
        assert all(r.id != "old-rec" for r in results)

    def test_store_strips_pii_from_summary(self, vector_mem):
        """Phone numbers in summaries must be masked before storing."""
        record = MemoryRecord(
            "r-pii", "e-pii", "user@example.com",
            "Call me at 13812345678 to discuss the project",
            datetime.now(timezone.utc),
        )
        vector_mem.store(record)
        results = vector_mem.search("Call me", top_k=1)
        assert "13812345678" not in results[0].summary


# ── UserPreferences ───────────────────────────────────────────────────────────


@pytest.fixture
def db_prefs(db_session):
    return UserPreferences(db_session)


class TestUserPreferences:
    def test_add_and_get_rule(self, db_prefs):
        db_prefs.add(PreferenceRule(
            rule_type="auto_label",
            rule_value={"sender": "boss@company.com", "label": "important"},
            source="explicit_config",
        ))
        rules = db_prefs.get_by_type("auto_label")
        assert len(rules) == 1
        assert rules[0].rule_value["label"] == "important"

    def test_record_manual_override(self, db_prefs):
        db_prefs.add(PreferenceRule(
            rule_type="block_sender",
            rule_value={"sender": "spam@spam.com"},
            source="manual_override",
        ))
        rules = db_prefs.get_by_type("block_sender")
        assert rules[0].source == "manual_override"

    def test_to_system_prompt_includes_rules(self, db_prefs):
        db_prefs.add(PreferenceRule(
            rule_type="auto_label",
            rule_value={"sender": "newsletter@news.com", "label": "newsletter"},
            source="explicit_config",
        ))
        prompt = db_prefs.to_system_prompt()
        assert "auto_label" in prompt
        assert "newsletter" in prompt

    def test_empty_preferences_returns_empty_prompt(self, db_prefs):
        prompt = db_prefs.to_system_prompt()
        assert isinstance(prompt, str)
