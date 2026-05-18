"""Tests for Phase 3 tools — written before implementation (TDD)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from email_agent.tools.email_tools import (
    ToolResult,
    ToolStatus,
    label_email,
    move_to_trash,
    permanently_delete,
    reply_email,
    forward_email,
)
from email_agent.tools.calendar_tools import (
    create_calendar_event,
    create_task,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _smtp_mock():
    m = MagicMock()
    m.send = AsyncMock()
    return m


# ── reply_email ───────────────────────────────────────────────────────────────


class TestReplyEmail:
    async def test_reply_sends_via_smtp(self):
        smtp = _smtp_mock()
        result = await reply_email(
            to="user@example.com",
            subject="Re: Hello",
            body="Got it, thanks.",
            idempotency_key="key-001",
            smtp_client=smtp,
        )
        assert result.status == ToolStatus.SUCCESS
        smtp.send.assert_called_once()

    async def test_reply_idempotency_prevents_duplicate_send(self):
        smtp = _smtp_mock()
        await reply_email(
            to="user@example.com", subject="Re: Hi", body="OK",
            idempotency_key="key-dup", smtp_client=smtp,
        )
        await reply_email(
            to="user@example.com", subject="Re: Hi", body="OK",
            idempotency_key="key-dup", smtp_client=smtp,
        )
        assert smtp.send.call_count == 1  # only sent once

    async def test_reply_smtp_error_returns_failure(self):
        smtp = _smtp_mock()
        smtp.send.side_effect = ConnectionError("SMTP down")
        result = await reply_email(
            to="user@example.com", subject="S", body="B",
            idempotency_key="key-err", smtp_client=smtp,
        )
        assert result.status == ToolStatus.FAILURE
        assert result.error is not None


# ── forward_email ─────────────────────────────────────────────────────────────


class TestForwardEmail:
    async def test_forward_sends_via_smtp(self):
        smtp = _smtp_mock()
        result = await forward_email(
            to="other@example.com",
            email_id="email-id-1",
            original_subject="Original",
            original_body="Original body",
            idempotency_key="fwd-001",
            smtp_client=smtp,
        )
        assert result.status == ToolStatus.SUCCESS
        smtp.send.assert_called_once()

    async def test_forward_idempotency(self):
        smtp = _smtp_mock()
        kwargs = dict(
            to="other@example.com", email_id="email-id-1",
            original_subject="S", original_body="B",
            idempotency_key="fwd-dup", smtp_client=smtp,
        )
        await forward_email(**kwargs)
        await forward_email(**kwargs)
        assert smtp.send.call_count == 1


# ── label_email ───────────────────────────────────────────────────────────────


class TestLabelEmail:
    async def test_label_returns_success(self):
        mock_repo = MagicMock()
        result = await label_email(
            email_id="email-id-1", label="important", repo=mock_repo
        )
        assert result.status == ToolStatus.SUCCESS

    async def test_label_calls_repo(self):
        mock_repo = MagicMock()
        await label_email(email_id="email-id-1", label="work", repo=mock_repo)
        mock_repo.add_label.assert_called_once_with("email-id-1", "work")


# ── move_to_trash ─────────────────────────────────────────────────────────────


class TestMoveToTrash:
    async def test_move_to_trash_requires_reason(self):
        mock_repo = MagicMock()
        mock_audit = MagicMock()
        result = await move_to_trash(
            email_id="email-id-1", reason="spam detected",
            repo=mock_repo, audit=mock_audit,
        )
        assert result.status == ToolStatus.SUCCESS

    async def test_move_to_trash_writes_audit_log(self):
        mock_repo = MagicMock()
        mock_audit = MagicMock()
        await move_to_trash(
            email_id="email-id-1", reason="user requested deletion",
            repo=mock_repo, audit=mock_audit,
        )
        mock_audit.log.assert_called_once()
        call_kwargs = mock_audit.log.call_args.kwargs
        assert call_kwargs.get("action") == "move_to_trash"
        assert call_kwargs.get("reason") == "user requested deletion"

    async def test_move_to_trash_calls_repo(self):
        mock_repo = MagicMock()
        mock_audit = MagicMock()
        await move_to_trash(
            email_id="email-id-1", reason="spam",
            repo=mock_repo, audit=mock_audit,
        )
        mock_repo.move_to_trash.assert_called_once_with("email-id-1")


# ── permanently_delete ────────────────────────────────────────────────────────


class TestPermanentlyDelete:
    async def test_not_confirmed_returns_confirmation_request(self):
        mock_repo = MagicMock()
        mock_audit = MagicMock()
        result = await permanently_delete(
            email_id="email-id-1", confirmed=False,
            reason="user wants to delete",
            repo=mock_repo, audit=mock_audit,
        )
        assert result.status == ToolStatus.PENDING_CONFIRMATION
        mock_repo.permanently_delete.assert_not_called()

    async def test_confirmed_executes_deletion(self):
        mock_repo = MagicMock()
        mock_audit = MagicMock()
        result = await permanently_delete(
            email_id="email-id-1", confirmed=True,
            reason="user confirmed",
            repo=mock_repo, audit=mock_audit,
        )
        assert result.status == ToolStatus.SUCCESS
        mock_repo.permanently_delete.assert_called_once_with("email-id-1")

    async def test_confirmed_deletion_writes_audit_log(self):
        mock_repo = MagicMock()
        mock_audit = MagicMock()
        await permanently_delete(
            email_id="email-id-1", confirmed=True,
            reason="confirmed delete",
            repo=mock_repo, audit=mock_audit,
        )
        mock_audit.log.assert_called_once()
        call_kwargs = mock_audit.log.call_args.kwargs
        assert call_kwargs.get("action") == "permanently_delete"

    async def test_unconfirmed_does_not_write_audit_log(self):
        """Audit log is written only when action actually executes."""
        mock_repo = MagicMock()
        mock_audit = MagicMock()
        await permanently_delete(
            email_id="email-id-1", confirmed=False,
            reason="pending",
            repo=mock_repo, audit=mock_audit,
        )
        mock_audit.log.assert_not_called()


# ── calendar_tools ────────────────────────────────────────────────────────────


class TestCreateCalendarEvent:
    async def test_returns_success(self):
        result = await create_calendar_event(
            title="Team meeting",
            start_time="2026-06-01T10:00:00",
            end_time="2026-06-01T11:00:00",
            participants=["a@example.com"],
        )
        assert result.status == ToolStatus.SUCCESS

    async def test_result_contains_event_id(self):
        result = await create_calendar_event(
            title="Sync", start_time="2026-06-01T10:00:00",
            end_time="2026-06-01T11:00:00", participants=[],
        )
        assert result.data is not None
        assert "event_id" in result.data


class TestCreateTask:
    async def test_returns_success(self):
        result = await create_task(
            title="Follow up", description="Send the report", due_date="2026-06-05"
        )
        assert result.status == ToolStatus.SUCCESS

    async def test_result_contains_task_id(self):
        result = await create_task(title="T", description="D", due_date="2026-06-10")
        assert result.data is not None
        assert "task_id" in result.data
