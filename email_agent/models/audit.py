"""Audit log model — immutable, append-only."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from email_agent.models.base import Base


class AuditEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    llm_chain: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="agent")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
