"""LLM output validation node — ensures intents are structurally valid."""

from email_agent.graph.nodes.classify import VALID_INTENT_NAMES
from email_agent.graph.state import GraphState


def validate_node(state: GraphState) -> GraphState:
    if not state.intents:
        return state.model_copy(update={"error": "No intents returned by classifier"})

    for intent in state.intents:
        if intent.name not in VALID_INTENT_NAMES:
            return state.model_copy(update={
                "error": f"Unknown intent name: {intent.name!r}"
            })

    return state.model_copy(update={"error": None})
