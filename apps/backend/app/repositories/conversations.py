from __future__ import annotations

import asyncio
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.models.chat import ConversationRecord, LearnerProfile


class ConversationRepository(Protocol):
    async def get(self, conversation_id: str) -> ConversationRecord | None: ...
    async def create_new(self) -> ConversationRecord: ...
    async def save(self, record: ConversationRecord) -> ConversationRecord: ...


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_schema_sync(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            turn_count INTEGER NOT NULL,
            subject TEXT,
            agent_id TEXT,
            learner_profile_json TEXT NOT NULL,
            message_history_json TEXT
        )
        """
    )
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()
    }
    if "agent_id" not in columns:
        conn.execute("ALTER TABLE conversations ADD COLUMN agent_id TEXT")
    conn.commit()


def _parse_iso(dt: str) -> datetime:
    parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _row_to_record(row: sqlite3.Row) -> ConversationRecord:
    learner = LearnerProfile.model_validate_json(row["learner_profile_json"])
    return ConversationRecord(
        id=row["id"],
        created_at=_parse_iso(row["created_at"]),
        updated_at=_parse_iso(row["updated_at"]),
        turn_count=row["turn_count"],
        subject=row["subject"],
        agent_id=row["agent_id"],
        learner_profile=learner,
        message_history_json=row["message_history_json"],
    )


def _record_to_tuple(record: ConversationRecord) -> tuple:
    return (
        record.id,
        record.created_at.isoformat(),
        record.updated_at.isoformat(),
        record.turn_count,
        record.subject,
        record.agent_id,
        record.learner_profile.model_dump_json(),
        record.message_history_json,
    )


class SqliteConversationRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def _with_conn(self, fn, *args, **kwargs):
        return await asyncio.to_thread(self._run_with_conn, fn, *args, **kwargs)

    def _run_with_conn(self, fn, *args, **kwargs):
        conn = _connect(self._db_path)
        try:
            _init_schema_sync(conn)
            return fn(conn, *args, **kwargs)
        finally:
            conn.close()

    async def get(self, conversation_id: str) -> ConversationRecord | None:
        def op(conn: sqlite3.Connection) -> ConversationRecord | None:
            cur = conn.execute(
                "SELECT * FROM conversations WHERE id = ?",
                (conversation_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return _row_to_record(row)

        return await self._with_conn(op)

    async def create_new(self) -> ConversationRecord:
        record = ConversationRecord(id=f"conv_{uuid.uuid4().hex}")
        await self.save(record)
        return record

    async def save(self, record: ConversationRecord) -> ConversationRecord:
        def op(conn: sqlite3.Connection) -> None:
            record.touch()
            conn.execute(
                """
                INSERT INTO conversations (
                    id, created_at, updated_at, turn_count, subject,
                    agent_id, learner_profile_json, message_history_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    turn_count = excluded.turn_count,
                    subject = excluded.subject,
                    agent_id = excluded.agent_id,
                    learner_profile_json = excluded.learner_profile_json,
                    message_history_json = excluded.message_history_json
                """,
                _record_to_tuple(record),
            )
            conn.commit()

        await self._with_conn(op)
        return record


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self._store: dict[str, ConversationRecord] = {}

    async def get(self, conversation_id: str) -> ConversationRecord | None:
        return self._store.get(conversation_id)

    async def create_new(self) -> ConversationRecord:
        record = ConversationRecord(id=f"conv_{uuid.uuid4().hex}")
        self._store[record.id] = record
        return record

    async def save(self, record: ConversationRecord) -> ConversationRecord:
        record.touch()
        self._store[record.id] = record
        return record
