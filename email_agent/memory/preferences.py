"""User preferences: explicit rules and manual overrides, injected into System Prompt."""

import enum
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Enum, String
from sqlalchemy.orm import Session
from sqlalchemy.types import Text

from email_agent.models.base import Base
from email_agent.models.email import GUID


class PreferenceSource(str, enum.Enum):
    manual_override = "manual_override"
    explicit_config = "explicit_config"


class UserPreferenceRow(Base):
    __tablename__ = "user_preferences"

    id = Column(GUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_type = Column(String, nullable=False, index=True)
    rule_value = Column(Text, nullable=False)   # JSON string
    source = Column(Enum(PreferenceSource), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


@dataclass
class PreferenceRule:
    rule_type: str
    rule_value: dict[str, Any]
    source: str


class UserPreferences:
    def __init__(self, session: Session):
        self._s = session

    def add(self, rule: PreferenceRule) -> None:
        row = UserPreferenceRow(
            rule_type=rule.rule_type,
            rule_value=json.dumps(rule.rule_value),
            source=PreferenceSource(rule.source),
        )
        self._s.add(row)
        self._s.commit()

    def get_by_type(self, rule_type: str) -> list[PreferenceRule]:
        rows = self._s.query(UserPreferenceRow).filter_by(rule_type=rule_type).all()
        return [
            PreferenceRule(
                rule_type=r.rule_type,
                rule_value=json.loads(r.rule_value),
                source=r.source,
            )
            for r in rows
        ]

    def to_system_prompt(self) -> str:
        rows = self._s.query(UserPreferenceRow).all()
        if not rows:
            return ""
        lines = ["User preferences:"]
        for r in rows:
            lines.append(f"  - [{r.rule_type}] {r.rule_value}")
        return "\n".join(lines)
