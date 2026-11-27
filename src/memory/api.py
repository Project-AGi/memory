"""The memory contract: what every AGi memory backend must honor.

AIVA (PC, AIVA, ROS2) and Aiko (Jetson, non-ROS) share this interface.
Backends store `Entry` dicts; the only writer is the owning agent process
(single-writer design - concurrency is the server's job, not the backend's).
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

KINDS = ('event', 'observation', 'dialogue', 'study', 'summary', 'reflection')

ENTRY_SCHEMA = {
    'ts': float,        # unix seconds
    'agent': str,       # 'aiva' | 'aiko' | ...
    'kind': str,        # one of KINDS
    'text': str,        # the content
    'tags': list,       # short strings, e.g. ['drawing', 'mug']
    'importance': float,  # 0..1
    'meta': dict,       # backend-specific extras (embedding, source topic, ...)
}


def normalize(entry, *, now=None) -> dict:
    """Fill defaults and validate one entry; raises ValueError on garbage."""
    if not isinstance(entry, dict):
        raise ValueError('Entry must be a dict')
    out = {
        'ts': float(entry.get('ts') or (now if now is not None else time.time())),
        'agent': str(entry.get('agent') or 'unknown'),
        'kind': entry.get('kind') or 'event',
        'text': str(entry.get('text') or '').strip(),
        'tags': [str(t) for t in (entry.get('tags') or [])],
        'importance': min(1.0, max(0.0, float(entry.get('importance', 0.5)))),
        'meta': dict(entry.get('meta') or {}),
    }
    if out['kind'] not in KINDS:
        raise ValueError(f'Unknown kind {out["kind"]!r}')
    if not out['text']:
        raise ValueError('Entry text is empty')
    return out


class MemoryBackend(ABC):
    """One writer process owns an instance; methods are synchronous."""

    @abstractmethod
    def append(self, entry: dict) -> dict:
        """Normalize, store, and return the stored entry."""

    @abstractmethod
    def search(self, query: str, *, limit: int = 8) -> list[dict]:
        """Best entries by relevance, importance, and recency."""

    @abstractmethod
    def recent(self, *, limit: int = 20, agent: str | None = None) -> list[dict]:
        """Newest entries first; optionally filtered by agent."""

    @abstractmethod
    def close(self) -> None:
        """Flush and release resources."""


def open_memory(uri: str, **kwargs) -> MemoryBackend:
    """Open a backend by URI: ``journal.jsonl`` -> journal, ``.db`` -> sqlite."""
    from .journal import JournalBackend
    from .sqlite_store import SqliteBackend
    if uri.endswith('.jsonl'):
        return JournalBackend(uri, **kwargs)
    if uri.endswith(('.db', '.sqlite', '.sqlite3')):
        return SqliteBackend(uri, **kwargs)
    raise ValueError(f'Unknown memory URI {uri!r} (.jsonl | .db)')
