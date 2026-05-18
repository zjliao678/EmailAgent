"""Short-term thread memory: stores per-thread conversation history with token guard."""

from typing import Callable, Optional


class ThreadMemory:
    def __init__(
        self,
        max_tokens: int = 8000,
        summarizer: Optional[Callable[[list[dict]], str]] = None,
    ):
        self._max_tokens = max_tokens
        self._summarizer = summarizer
        self._store: dict[str, list[dict]] = {}

    def add(self, thread_id: str, role: str, content: str) -> None:
        self._store.setdefault(thread_id, []).append(
            {"role": role, "content": content}
        )

    def get(self, thread_id: str) -> list[dict]:
        messages = self._store.get(thread_id, [])
        if not messages:
            return []
        if self._summarizer and self._estimate_tokens(messages) > self._max_tokens:
            summary = self._summarizer(messages)
            compressed = [{"role": "system", "content": f"[Summary] {summary}"}]
            self._store[thread_id] = compressed
            return compressed
        return list(messages)

    def clear(self, thread_id: str) -> None:
        self._store.pop(thread_id, None)

    @staticmethod
    def _estimate_tokens(messages: list[dict]) -> int:
        # Rough estimate: 1 token ≈ 4 chars
        return sum(len(m.get("content", "")) for m in messages) // 4
