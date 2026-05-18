"""Phase 6 tests — Audit log, Log sanitization."""

import logging
import pytest
from datetime import datetime, timezone

from email_agent.audit.repository import AuditRepository
from email_agent.logging_config import SanitizingFilter


# ── Audit Log (6.3) ───────────────────────────────────────────────────────────

class TestAuditRepository:
    def test_log_creates_entry(self, db_session):
        repo = AuditRepository(db_session)
        entry = repo.log(action="move_to_trash", email_id="e-1", reason="spam")
        assert entry is not None
        assert entry.id is not None

    def test_entry_has_correct_fields(self, db_session):
        repo = AuditRepository(db_session)
        entry = repo.log(
            action="permanently_delete",
            email_id="e-2",
            reason="GDPR",
            llm_chain={"intent": "permanently_delete"},
            source="agent",
        )
        assert entry.action == "permanently_delete"
        assert entry.email_id == "e-2"
        assert entry.reason == "GDPR"
        assert entry.source == "agent"

    def test_created_at_is_set(self, db_session):
        repo = AuditRepository(db_session)
        entry = repo.log(action="move_to_trash", email_id="e-3", reason="old")
        assert isinstance(entry.created_at, datetime)

    def test_get_by_action_filters_correctly(self, db_session):
        repo = AuditRepository(db_session)
        repo.log(action="move_to_trash", email_id="e-a", reason="x")
        repo.log(action="permanently_delete", email_id="e-b", reason="y")
        repo.log(action="move_to_trash", email_id="e-c", reason="z")
        entries = repo.get_by_action("move_to_trash")
        assert len(entries) == 2
        assert all(e.action == "move_to_trash" for e in entries)

    def test_audit_repository_has_no_delete_method(self, db_session):
        """Audit entries are immutable — no delete method on repository."""
        repo = AuditRepository(db_session)
        assert not hasattr(repo, "delete")
        assert not hasattr(repo, "update")

    def test_multiple_actions_logged_independently(self, db_session):
        repo = AuditRepository(db_session)
        for i in range(3):
            repo.log(action="move_to_trash", email_id=f"e-{i}", reason="bulk")
        assert len(repo.get_by_action("move_to_trash")) == 3


# ── Log Sanitization (6.2) ────────────────────────────────────────────────────

class TestSanitizingFilter:
    def _make_record(self, msg, args=()):
        return logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=msg, args=args, exc_info=None,
        )

    def test_email_body_content_masked(self):
        filt = SanitizingFilter()
        record = self._make_record(
            "Processing: <email_content>Top secret content</email_content>"
        )
        filt.filter(record)
        assert "Top secret content" not in record.msg

    def test_email_address_masked(self):
        filt = SanitizingFilter()
        record = self._make_record("Sender: alice@company.com replied")
        filt.filter(record)
        assert "alice@company.com" not in record.msg

    def test_chinese_phone_masked(self):
        filt = SanitizingFilter()
        record = self._make_record("Contact: 13812345678 for details")
        filt.filter(record)
        assert "13812345678" not in record.msg

    def test_normal_message_passes_through(self):
        filt = SanitizingFilter()
        record = self._make_record("Email id=abc-123 processed successfully")
        filt.filter(record)
        assert "abc-123" in record.msg
        assert "processed successfully" in record.msg

    def test_args_with_email_address_masked(self):
        filt = SanitizingFilter()
        record = self._make_record("Sender: %s", args=("bob@example.com",))
        filt.filter(record)
        assert "bob@example.com" not in str(record.args)
