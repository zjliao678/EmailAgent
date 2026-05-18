"""Risk classification node — assigns RiskLevel to each intent and to the state."""

from email_agent.graph.state import GraphState, Intent, RiskLevel

_RISK_MAP: dict[str, RiskLevel] = {
    "label": RiskLevel.LOW,
    "archive": RiskLevel.LOW,
    "mark_read": RiskLevel.LOW,
    "create_calendar_event": RiskLevel.LOW,
    "create_task": RiskLevel.LOW,
    "reply": RiskLevel.MEDIUM,
    "forward": RiskLevel.MEDIUM,
    "move_to_trash": RiskLevel.HIGH,
    "permanently_delete": RiskLevel.HIGH,
}


def risk_node(state: GraphState) -> GraphState:
    scored: list[Intent] = []
    overall = RiskLevel.LOW

    for intent in state.intents:
        level = _RISK_MAP.get(intent.name, RiskLevel.HIGH)  # unknown → HIGH by default
        scored.append(intent.model_copy(update={"risk_level": level}))
        if level > overall:
            overall = level

    return state.model_copy(update={"intents": scored, "risk_level": overall})
