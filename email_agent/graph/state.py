from enum import IntEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class RiskLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class Intent(BaseModel):
    name: str
    entities: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    risk_level: Optional[RiskLevel] = None


class GraphState(BaseModel):
    # ── Email metadata ────────────────────────────────────────────────────────
    email_id: str
    message_id: str
    sender: str
    subject: str
    body: str  # always wrapped in <email_content> tags

    # ── Processing state ──────────────────────────────────────────────────────
    intents: list[Intent] = Field(default_factory=list)
    risk_level: Optional[RiskLevel] = None
    injection_detected: bool = False
    error: Optional[str] = None
    human_confirmed: Optional[bool] = None  # for high-risk actions
