"""Long-term vector memory: ChromaDB-backed email summaries with PII masking and TTL."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from email_agent.ingestion.parser import mask_pii

_COLLECTION = "email_summaries"
_TTL_DAYS = 90


@dataclass
class MemoryRecord:
    id: str
    email_id: str
    sender: str
    summary: str
    created_at: datetime


class VectorMemory:
    def __init__(self, client):
        self._col = client.get_or_create_collection(_COLLECTION)

    def store(self, record: MemoryRecord) -> None:
        clean_summary = mask_pii(record.summary)
        ts = record.created_at.timestamp()
        self._col.upsert(
            ids=[record.id],
            documents=[clean_summary],
            metadatas=[{
                "email_id": record.email_id,
                "sender": record.sender,
                "created_at": record.created_at.isoformat(),
                "created_at_ts": ts,
                "summary": clean_summary,
            }],
        )

    def search(self, query: str, top_k: int = 5) -> list[MemoryRecord]:
        cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=_TTL_DAYS)).timestamp()
        count = self._col.count()
        if count == 0:
            return []
        try:
            res = self._col.query(
                query_texts=[query],
                n_results=min(top_k, count),
                where={"created_at_ts": {"$gte": cutoff_ts}},
            )
        except Exception:
            return []

        records = []
        if res["ids"] and res["ids"][0]:
            for rid, meta in zip(res["ids"][0], res["metadatas"][0]):
                records.append(MemoryRecord(
                    id=rid,
                    email_id=meta["email_id"],
                    sender=meta["sender"],
                    summary=meta["summary"],
                    created_at=datetime.fromisoformat(meta["created_at"]),
                ))
        return records

    def delete_by_sender(self, sender: str) -> None:
        """Right-to-be-forgotten: remove all records for a given sender."""
        self._col.delete(where={"sender": {"$eq": sender}})
