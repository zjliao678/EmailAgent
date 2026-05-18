"""Audit repository — append-only, no update or delete operations."""

import json
from typing import Optional

from sqlalchemy.orm import Session

from email_agent.models.audit import AuditEntry


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def log(
        self,
        *,
        action: str,
        email_id: str,
        reason: str,
        llm_chain: Optional[dict] = None,
        source: str = "agent",
    ) -> AuditEntry:
        entry = AuditEntry(
            action=action,
            email_id=email_id,
            reason=reason,
            llm_chain=json.dumps(llm_chain) if llm_chain else None,
            source=source,
        )
        self._session.add(entry)
        self._session.flush()
        return entry

    def get_by_action(self, action: str) -> list[AuditEntry]:
        return (
            self._session.query(AuditEntry)
            .filter(AuditEntry.action == action)
            .order_by(AuditEntry.created_at)
            .all()
        )
