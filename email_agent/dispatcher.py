"""Dispatch classified intents to concrete tool calls.

Auto-executed intents: move_to_trash, archive, mark_read, label.
Deferred intents (require LLM generation or human confirmation):
  reply, forward, create_calendar_event, create_task, permanently_delete.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from email_agent.graph.state import GraphState, Intent, RiskLevel
from email_agent.tools.email_tools import (
    move_to_trash,
    label_email,
    ToolResult,
    ToolStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    intent_name: str
    status: str          # "executed" | "deferred" | "skipped" | "error"
    detail: Optional[str] = None


async def dispatch(
    state: GraphState,
    repo,
    audit,
    smtp_client=None,
) -> list[DispatchResult]:
    """Execute safe auto-actions; log deferred actions for human review."""
    results: list[DispatchResult] = []

    for intent in state.intents:
        result = await _handle_intent(intent, state, repo, audit, smtp_client)
        results.append(result)
        logger.info(
            "dispatch email_id=%s intent=%s status=%s detail=%s",
            state.email_id, intent.name, result.status, result.detail,
        )

    return results


async def _handle_intent(
    intent: Intent,
    state: GraphState,
    repo,
    audit,
    smtp_client,
) -> DispatchResult:
    name = intent.name

    if state.risk_level == RiskLevel.HIGH and name not in ("label", "archive", "mark_read"):
        return DispatchResult(name, "skipped", "high-risk — awaiting human confirmation")

    if name == "move_to_trash":
        result: ToolResult = await move_to_trash(
            email_id=state.email_id,
            reason=intent.reason or "classified as trash by agent",
            repo=repo,
            audit=audit,
        )
        status = "executed" if result.status == ToolStatus.SUCCESS else "error"
        return DispatchResult(name, status, result.error)

    if name == "label":
        label_value = intent.entities.get("label", "auto-labelled")
        result = await label_email(email_id=state.email_id, label=label_value, repo=repo)
        status = "executed" if result.status == ToolStatus.SUCCESS else "error"
        return DispatchResult(name, status, result.error)

    if name in ("archive", "mark_read"):
        # Stub: log as deferred until IMAP flag-setting is wired up
        return DispatchResult(name, "deferred", "IMAP flag action — not yet wired")

    if name in ("reply", "forward"):
        return DispatchResult(name, "deferred", "needs LLM content generation")

    if name in ("create_calendar_event", "create_task"):
        return DispatchResult(name, "deferred", "needs calendar/task integration")

    if name == "permanently_delete":
        return DispatchResult(name, "skipped", "requires explicit human confirmation")

    return DispatchResult(name, "skipped", f"unknown intent: {name}")
