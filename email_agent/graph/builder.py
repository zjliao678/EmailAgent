"""LangGraph graph builder for the EmailAgent decision pipeline."""

from typing import Literal

from langgraph.graph import StateGraph, END

from email_agent.graph.state import GraphState, RiskLevel
from email_agent.graph.nodes.injection_check import injection_check_node
from email_agent.graph.nodes.classify import classify_node
from email_agent.graph.nodes.validate import validate_node
from email_agent.graph.nodes.split import split_node
from email_agent.graph.nodes.risk import risk_node


# ── Routing functions ─────────────────────────────────────────────────────────


def _after_injection_check(state: GraphState) -> Literal["classify", "abort"]:
    return "abort" if state.injection_detected else "classify"


def _after_validate(state: GraphState) -> Literal["split", "abort"]:
    return "abort" if state.error else "split"


def _after_risk(state: GraphState) -> Literal["execute", "preview", "confirm"]:
    if state.risk_level == RiskLevel.HIGH:
        return "confirm"
    if state.risk_level == RiskLevel.MEDIUM:
        return "preview"
    return "execute"


# ── Stub nodes (Phase 3 will replace these) ───────────────────────────────────


def _abort_node(state: GraphState) -> GraphState:
    return state


def _execute_node(state: GraphState) -> GraphState:
    return state


def _preview_node(state: GraphState) -> GraphState:
    return state


def _confirm_node(state: GraphState) -> GraphState:
    return state


# ── Graph assembly ────────────────────────────────────────────────────────────


def build_graph():
    g = StateGraph(GraphState)

    g.add_node("injection_check", injection_check_node)
    g.add_node("classify", classify_node)
    g.add_node("validate", validate_node)
    g.add_node("split", split_node)
    g.add_node("risk", risk_node)
    g.add_node("execute", _execute_node)
    g.add_node("preview", _preview_node)
    g.add_node("confirm", _confirm_node)
    g.add_node("abort", _abort_node)

    g.set_entry_point("injection_check")

    g.add_conditional_edges("injection_check", _after_injection_check)
    g.add_edge("classify", "validate")
    g.add_conditional_edges("validate", _after_validate)
    g.add_edge("split", "risk")
    g.add_conditional_edges("risk", _after_risk)

    for terminal in ("execute", "preview", "confirm", "abort"):
        g.add_edge(terminal, END)

    return g.compile()
