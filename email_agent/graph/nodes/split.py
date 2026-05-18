"""Multi-intent split node — preserves ordered intent list for serial execution."""

from email_agent.graph.state import GraphState


def split_node(state: GraphState) -> GraphState:
    # Intents are already an ordered list from classify_node.
    # This node is a no-op for now; future work may reorder or filter.
    return state
