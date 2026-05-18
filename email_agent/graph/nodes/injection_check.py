"""Prompt injection detection node — first guard in the pipeline."""

import re

from email_agent.graph.state import GraphState

# Patterns known to be used in prompt injection attacks
_INJECTION_PATTERNS = [
    r"ignore\s+(?:previous|prior|all)\s+instructions?",
    r"disregard\b.{0,50}\binstructions?",
    r"forward\s+all\s+(?:emails?|messages?|mails?)",
    r"you\s+are\s+now\s+(?:a|an)",
    r"new\s+instructions?:",
    r"act\s+as\s+(?:a|an|if)",
    r"system\s*:\s*you",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def injection_check_node(state: GraphState) -> GraphState:
    for pattern in _COMPILED:
        if pattern.search(state.body):
            return state.model_copy(update={
                "injection_detected": True,
                "error": f"Prompt injection detected in email {state.message_id}",
            })
    return state.model_copy(update={"injection_detected": False})
