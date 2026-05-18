"""Tests for email_agent.ingestion.dedup — written before implementation (TDD)."""

import pytest

from email_agent.ingestion.dedup import EmailRepository
from email_agent.models.email import EmailStatus


class TestEmailRepository:
    def test_new_message_is_not_duplicate(self, db_session):
        repo = EmailRepository(db_session)
        assert repo.is_duplicate("<new-001@example.com>") is False

    def test_in_progress_message_is_duplicate(self, db_session):
        repo = EmailRepository(db_session)
        repo.try_acquire("<msg-001@example.com>", sender="a@b.com", subject="Hi")
        assert repo.is_duplicate("<msg-001@example.com>") is True

    def test_done_message_is_duplicate(self, db_session):
        repo = EmailRepository(db_session)
        email_id = repo.try_acquire("<msg-002@example.com>", sender="a@b.com", subject="Hi")
        repo.mark_done(email_id)
        assert repo.is_duplicate("<msg-002@example.com>") is True

    def test_failed_message_is_not_duplicate_allows_retry(self, db_session):
        repo = EmailRepository(db_session)
        email_id = repo.try_acquire("<msg-003@example.com>", sender="a@b.com", subject="Hi")
        repo.mark_failed(email_id)
        # Should be retryable
        assert repo.is_duplicate("<msg-003@example.com>") is False

    def test_try_acquire_returns_email_id(self, db_session):
        repo = EmailRepository(db_session)
        email_id = repo.try_acquire("<msg-004@example.com>", sender="a@b.com", subject="Hi")
        assert email_id is not None

    def test_try_acquire_returns_none_when_in_progress(self, db_session):
        repo = EmailRepository(db_session)
        repo.try_acquire("<msg-005@example.com>", sender="a@b.com", subject="Hi")
        result = repo.try_acquire("<msg-005@example.com>", sender="a@b.com", subject="Hi")
        assert result is None

    def test_try_acquire_returns_none_when_done(self, db_session):
        repo = EmailRepository(db_session)
        email_id = repo.try_acquire("<msg-006@example.com>", sender="a@b.com", subject="Hi")
        repo.mark_done(email_id)
        result = repo.try_acquire("<msg-006@example.com>", sender="a@b.com", subject="Hi")
        assert result is None

    def test_try_acquire_retries_failed_message(self, db_session):
        repo = EmailRepository(db_session)
        email_id = repo.try_acquire("<msg-007@example.com>", sender="a@b.com", subject="Hi")
        repo.mark_failed(email_id)
        new_id = repo.try_acquire("<msg-007@example.com>", sender="a@b.com", subject="Hi")
        assert new_id is not None

    def test_mark_done_sets_correct_status(self, db_session):
        repo = EmailRepository(db_session)
        email_id = repo.try_acquire("<msg-008@example.com>", sender="a@b.com", subject="Hi")
        repo.mark_done(email_id)
        record = repo.get_by_id(email_id)
        assert record.status == EmailStatus.done

    def test_mark_failed_sets_correct_status(self, db_session):
        repo = EmailRepository(db_session)
        email_id = repo.try_acquire("<msg-009@example.com>", sender="a@b.com", subject="Hi")
        repo.mark_failed(email_id)
        record = repo.get_by_id(email_id)
        assert record.status == EmailStatus.failed

    def test_get_by_id_returns_none_for_unknown(self, db_session):
        repo = EmailRepository(db_session)
        assert repo.get_by_id("non-existent-id") is None
