"""SQLite-backed conversation history with a bounded recent context window."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4


class ConversationStore:
    """Persist recent user and assistant turns in a local SQLite database."""

    def __init__(
        self,
        database_path: str | Path,
        max_turns: int = 8,
        *,
        default_title: str = "Chat",
    ) -> None:
        self.database_path = Path(database_path).expanduser()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_turns = max(1, max_turns)
        self.conversation_id = "default"
        self.default_title = default_title
        self._initialize_conversations()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database_path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys = ON")
            with db:
                yield db
        finally:
            db.close()

    def _initialize_conversations(self) -> None:
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS conversations ("
                "id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS conversation_turns ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "conversation_id TEXT NOT NULL REFERENCES conversations(id), "
                "exchange_id TEXT NOT NULL, "
                "role TEXT NOT NULL CHECK (role IN ('user', 'assistant')), "
                "content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS conversation_turns_order "
                "ON conversation_turns (conversation_id, id DESC)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS conversation_events ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "conversation_id TEXT NOT NULL REFERENCES conversations(id), "
                "kind TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}', "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS conversation_events_order "
                       "ON conversation_events (conversation_id, kind, id DESC)")
            db.execute(
                "INSERT OR IGNORE INTO conversations (id, title) VALUES (?, ?)",
                (self.conversation_id, self.default_title),
            )

    def recent(self, conversation_id: str | None = None) -> list[dict[str, str]]:
        active_conversation = conversation_id or self.conversation_id
        with self._connect() as db:
            rows = db.execute(
                "SELECT role, content FROM conversation_turns "
                "WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
                (active_conversation, self.max_turns * 2),
            ).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def add_exchange(
        self,
        user_text: str,
        assistant_text: str,
        conversation_id: str | None = None,
    ) -> None:
        active_conversation = conversation_id or self.conversation_id
        exchange_id = str(uuid4())
        title = (
            self.default_title
            if active_conversation == self.conversation_id
            else f"Conversation {active_conversation}"
        )
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO conversations (id, title) VALUES (?, ?)",
                (active_conversation, title),
            )
            db.executemany(
                "INSERT INTO conversation_turns "
                "(conversation_id, exchange_id, role, content) VALUES (?, ?, ?, ?)",
                [
                    (active_conversation, exchange_id, "user", user_text),
                    (active_conversation, exchange_id, "assistant", assistant_text),
                ],
            )

    def record_event(self, text: str, *, kind: str = 'event', metadata: dict | None = None) -> None:
        """Persist an agent action alongside conversation history, without inventing dialogue."""
        import json
        if not isinstance(text, str) or not text.strip() or len(text) > 32000:
            raise ValueError('Event text must contain 1–32000 characters')
        if not isinstance(kind, str) or not 1 <= len(kind) <= 64:
            raise ValueError('Event kind must contain 1–64 characters')
        encoded = json.dumps(metadata or {}, ensure_ascii=False, allow_nan=False)
        if len(encoded) > 64000:
            raise ValueError('Event metadata exceeds 64000 characters')
        with self._connect() as db:
            db.execute('INSERT INTO conversation_events (conversation_id, kind, content, metadata) '
                       'VALUES (?, ?, ?, ?)', (self.conversation_id, kind, text, encoded))

    def recall_events(self, query: str = '', *, kind: str = 'event', limit: int = 8) -> list[dict]:
        """Recall related/recent actions from this conversation, including after restart."""
        import json
        import re
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError('Event recall limit must be 1–20')
        terms = list(dict.fromkeys(re.findall(r'\w+', query.casefold())))[:24]
        # Parameterized LIKE search; escape its wildcard characters in query terms.
        matches = ['%' + term.replace('_', r'\_') + '%' for term in terms]
        score = ' + '.join("CASE WHEN lower(content) LIKE ? ESCAPE '\\' THEN 1 ELSE 0 END" for _ in matches) or '0'
        with self._connect() as db:
            rows = db.execute(
                f'SELECT content, metadata, created_at FROM conversation_events '
                f'WHERE conversation_id = ? AND kind = ? ORDER BY ({score}) DESC, id DESC LIMIT ?',
                (self.conversation_id, kind, *matches, limit),
            ).fetchall()
        return [{'text': row[0], 'metadata': json.loads(row[1]), 'created_at': row[2]} for row in rows]
