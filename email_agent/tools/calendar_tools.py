"""Calendar and task creation tools."""

import uuid

from email_agent.tools.email_tools import ToolResult, ToolStatus


async def create_calendar_event(
    *,
    title: str,
    start_time: str,
    end_time: str,
    participants: list[str],
) -> ToolResult:
    # Stub: in Phase 6 this calls Google Calendar / Exchange API
    event_id = str(uuid.uuid4())
    return ToolResult(
        status=ToolStatus.SUCCESS,
        data={"event_id": event_id, "title": title, "start_time": start_time},
    )


async def create_task(
    *,
    title: str,
    description: str,
    due_date: str,
) -> ToolResult:
    # Stub: in Phase 6 this calls a task management API
    task_id = str(uuid.uuid4())
    return ToolResult(
        status=ToolStatus.SUCCESS,
        data={"task_id": task_id, "title": title, "due_date": due_date},
    )
