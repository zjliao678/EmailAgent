"""Email deduplication and processing state machine backed by SQLAlchemy."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from email_agent.models.email import Email, EmailStatus


class EmailRepository:
    def __init__(self, session: Session):
        self._s = session

    # ── Read ──────────────────────────────────────────────────────────────────

    def is_duplicate(self, message_id: str) -> bool:
        """Return True if this message_id is already in_progress or done."""
        record = self._s.query(Email).filter_by(message_id=message_id).first()
        if record is None:
            return False
        return record.status in (EmailStatus.in_progress, EmailStatus.done)

    def get_by_id(self, email_id: str) -> Optional[Email]:
        return self._s.get(Email, email_id)

    # ── Write ─────────────────────────────────────────────────────────────────

    def try_acquire(
        self,
        message_id: str,
        *,
        sender: str = "",
        subject: str = "",
        thread_id: str = "",
        received_at: Optional[datetime] = None,
    ) -> Optional[str]:
        """Atomically acquire processing rights for a message.

        Returns the email_id (str) if acquired, or None if the message is
        already in_progress / done (i.e. another worker has it).
        Failed messages are re-queued for retry.
        """
        existing = self._s.query(Email).filter_by(message_id=message_id).first()

        if existing is not None:
            if existing.status in (EmailStatus.in_progress, EmailStatus.done):
                return None
            # status == failed → retry
            existing.status = EmailStatus.in_progress
            existing.updated_at = datetime.now(timezone.utc)
            self._s.commit()
            return existing.id

        record = Email(
            id=str(uuid.uuid4()),
            message_id=message_id,
            sender=sender,
            subject=subject,
            thread_id=thread_id,
            received_at=received_at or datetime.now(timezone.utc),
            status=EmailStatus.in_progress,
        )
        try:
            self._s.add(record)
            self._s.commit()
            return record.id
        except IntegrityError:
            # Race condition: another worker inserted first
            self._s.rollback()
            return None

    def mark_done(self, email_id: str) -> None:
        self._set_status(email_id, EmailStatus.done)

    def mark_failed(self, email_id: str) -> None:
        self._set_status(email_id, EmailStatus.failed)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _set_status(self, email_id: str, status: EmailStatus) -> None:
        record = self._s.get(Email, email_id)
        if record:
            record.status = status
            record.updated_at = datetime.now(timezone.utc)
            self._s.commit()
