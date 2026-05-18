import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, String
from sqlalchemy.types import CHAR, TypeDecorator

from .base import Base


class GUID(TypeDecorator):
    """UUID stored as CHAR(36); compatible with both PostgreSQL and SQLite."""

    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return value  # return as str; callers do not need uuid.UUID objects


class EmailStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    failed = "failed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Email(Base):
    __tablename__ = "emails"

    id = Column(GUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String, unique=True, nullable=False, index=True)
    thread_id = Column(String)
    sender = Column(String)
    subject = Column(String)
    received_at = Column(DateTime(timezone=True))
    status = Column(Enum(EmailStatus), default=EmailStatus.pending, nullable=False)
    idempotency_key = Column(String)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
