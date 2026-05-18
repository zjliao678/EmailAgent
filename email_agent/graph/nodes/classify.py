"""Intent classification node — calls LLM (DeepSeek, OpenAI-compatible) with retry."""

import logging
from typing import Any, Callable, Optional

from pydantic import BaseModel

from email_agent.graph.state import GraphState, Intent

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3

VALID_INTENT_NAMES = frozenset({
    "reply", "forward", "label", "move_to_trash", "permanently_delete",
    "create_calendar_event", "create_task", "archive", "mark_read",
})


class ClassifyResult(BaseModel):
    intents: list[Intent]
    reason: str


def classify_node(
    state: GraphState,
    llm: Optional[Callable[[GraphState], ClassifyResult]] = None,
) -> GraphState:
    """Call LLM to classify email intents. Retries up to 3 times on failure."""
    if llm is None:
        llm = _default_llm()

    last_error: Optional[Exception] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = llm(state)
            if not isinstance(result, ClassifyResult):
                raise ValueError(f"Expected ClassifyResult, got {type(result)}")
            return state.model_copy(update={"intents": result.intents})
        except Exception as exc:
            last_error = exc
            logger.warning("classify_node attempt %d/%d failed: %s", attempt, _MAX_RETRIES, exc)

    return state.model_copy(update={
        "intents": [],
        "error": f"Classification failed after {_MAX_RETRIES} attempts: {last_error}",
    })


def _default_llm() -> Callable[[GraphState], ClassifyResult]:
    """Build the real LLM callable (deferred import so tests never load langchain)."""
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from email_agent.config import get_settings

    cfg = get_settings()
    llm = ChatOpenAI(
        model=cfg.llm_model,
        temperature=cfg.llm_temperature,
        base_url=cfg.llm_base_url,
        api_key=cfg.deepseek_api_key,
    ).with_structured_output(ClassifyResult)
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an email intent classifier. "
            "Return a JSON object with 'intents' (list) and 'reason' (string). "
            f"Valid intent names: {sorted(VALID_INTENT_NAMES)}"
        )),
        ("human", "Email subject: {subject}\n\nBody:\n{body}"),
    ])
    chain = prompt | llm

    def call(state: GraphState) -> ClassifyResult:
        return chain.invoke({"subject": state.subject, "body": state.body})

    return call
