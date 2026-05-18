"""Email action tools: reply, forward, label, move_to_trash, permanently_delete."""

import enum
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# In-memory idempotency store (replaced by Redis/DB in production)
_sent_keys: set[str] = set()


class ToolStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING_CONFIRMATION = "pending_confirmation"


@dataclass
class ToolResult:
    status: ToolStatus
    data: Optional[dict[str, Any]] = None
    error: Optional[str] = None


# ── reply_email ───────────────────────────────────────────────────────────────


async def reply_email(
    *,
    to: str,
    subject: str,
    body: str,
    idempotency_key: str,
    smtp_client,
) -> ToolResult:
    if idempotency_key in _sent_keys:
        logger.info("reply_email: idempotency hit for key=%s", idempotency_key)
        return ToolResult(status=ToolStatus.SUCCESS, data={"idempotent": True})
    try:
        await smtp_client.send(to=to, subject=subject, body=body)
        _sent_keys.add(idempotency_key)
        return ToolResult(status=ToolStatus.SUCCESS)
    except Exception as exc:
        logger.error("reply_email failed: %s", exc)
        return ToolResult(status=ToolStatus.FAILURE, error=str(exc))


# ── forward_email ─────────────────────────────────────────────────────────────


async def forward_email(
    *,
    to: str,
    email_id: str,
    original_subject: str,
    original_body: str,
    idempotency_key: str,
    smtp_client,
) -> ToolResult:
    if idempotency_key in _sent_keys:
        return ToolResult(status=ToolStatus.SUCCESS, data={"idempotent": True})
    try:
        subject = f"Fwd: {original_subject}"
        body = f"---------- Forwarded message ----------\n{original_body}"
        await smtp_client.send(to=to, subject=subject, body=body)
        _sent_keys.add(idempotency_key)
        return ToolResult(status=ToolStatus.SUCCESS)
    except Exception as exc:
        logger.error("forward_email failed: %s", exc)
        return ToolResult(status=ToolStatus.FAILURE, error=str(exc))


# ── label_email ───────────────────────────────────────────────────────────────


async def label_email(*, email_id: str, label: str, repo) -> ToolResult:
    repo.add_label(email_id, label)
    return ToolResult(status=ToolStatus.SUCCESS)


# ── move_to_trash ─────────────────────────────────────────────────────────────


async def move_to_trash(*, email_id: str, reason: str, repo, audit) -> ToolResult:
    repo.move_to_trash(email_id)
    audit.log(
        action="move_to_trash",
        email_id=email_id,
        reason=reason,
        operator="agent",
    )
    return ToolResult(status=ToolStatus.SUCCESS)


# ── permanently_delete ────────────────────────────────────────────────────────


async def permanently_delete(
    *, email_id: str, confirmed: bool, reason: str, repo, audit
) -> ToolResult:
    if not confirmed:
        return ToolResult(
            status=ToolStatus.PENDING_CONFIRMATION,
            data={"email_id": email_id, "action": "permanently_delete", "reason": reason},
        )
    repo.permanently_delete(email_id)
    audit.log(
        action="permanently_delete",
        email_id=email_id,
        reason=reason,
        operator="agent",
    )
    return ToolResult(status=ToolStatus.SUCCESS)
