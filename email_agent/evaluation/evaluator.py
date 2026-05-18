"""Phase 5 evaluation infrastructure: Golden Dataset loader and accuracy evaluator."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

from email_agent.graph.state import GraphState, Intent
from email_agent.graph.nodes.classify import classify_node, ClassifyResult

ACCURACY_THRESHOLD = 0.95


@dataclass
class EvalSample:
    id: str
    subject: str
    body: str
    sender: str
    expected_intents: list[str]
    is_injection: bool = False


@dataclass
class EvalResult:
    sample_id: str
    expected: set[str]
    actual: set[str]
    correct: bool


@dataclass
class EvalReport:
    accuracy: float
    results: list[EvalResult] = field(default_factory=list)


def load_samples(path: Path) -> list[EvalSample]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        EvalSample(
            id=s["id"],
            subject=s["subject"],
            body=s["body"],
            sender=s["sender"],
            expected_intents=s.get("expected_intents", []),
            is_injection=s.get("is_injection", False),
        )
        for s in data["samples"]
    ]


def run_evaluation(samples: list[EvalSample], llm_fn: Callable) -> EvalReport:
    """Run classify_node over non-injection samples and measure accuracy."""
    classify_samples = [s for s in samples if not s.is_injection]
    if not classify_samples:
        return EvalReport(accuracy=0.0)

    results = []
    for sample in classify_samples:
        state = GraphState(
            email_id=sample.id,
            message_id=f"<{sample.id}@golden>",
            sender=sample.sender,
            subject=sample.subject,
            body=sample.body,
        )
        output = classify_node(state, llm=llm_fn)
        actual = {i.name for i in output.intents}
        expected = set(sample.expected_intents)
        results.append(EvalResult(
            sample_id=sample.id,
            expected=expected,
            actual=actual,
            correct=actual == expected,
        ))

    accuracy = sum(r.correct for r in results) / len(results)
    return EvalReport(accuracy=accuracy, results=results)
