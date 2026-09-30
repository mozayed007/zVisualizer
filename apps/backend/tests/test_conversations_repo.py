from __future__ import annotations

import pytest

from app.models.chat import ConversationRecord
from app.repositories.conversations import InMemoryConversationRepository, SqliteConversationRepository


@pytest.mark.asyncio
async def test_in_memory_get_create_save_roundtrip() -> None:
    repo = InMemoryConversationRepository()
    created = await repo.create_new()
    loaded = await repo.get(created.id)
    assert loaded is not None
    assert loaded.id == created.id

    loaded.turn_count = 3
    await repo.save(loaded)
    again = await repo.get(created.id)
    assert again is not None
    assert again.turn_count == 3


@pytest.mark.asyncio
async def test_sqlite_roundtrip(tmp_path) -> None:
    db = tmp_path / "conv.db"
    repo = SqliteConversationRepository(db)
    created = await repo.create_new()
    loaded = await repo.get(created.id)
    assert loaded is not None
    assert loaded.id == created.id

    loaded.turn_count = 2
    loaded.message_history_json = '{"ok":true}'
    await repo.save(loaded)
    again = await repo.get(created.id)
    assert again is not None
    assert again.turn_count == 2
    assert again.message_history_json == '{"ok":true}'


@pytest.mark.asyncio
async def test_sqlite_missing_returns_none(tmp_path) -> None:
    repo = SqliteConversationRepository(tmp_path / "empty.db")
    assert await repo.get("conv_nonexistent") is None


@pytest.mark.asyncio
async def test_sqlite_rebuilds_outdated_schema(tmp_path) -> None:
    import sqlite3

    db = tmp_path / "outdated.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            turn_count INTEGER NOT NULL,
            subject TEXT,
            message_history_json TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO conversations (id, created_at, updated_at, turn_count, subject, message_history_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("conv_outdated", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", 1, "systems", None),
    )
    conn.commit()
    conn.close()

    repo = SqliteConversationRepository(db)
    assert await repo.get("conv_outdated") is None

    columns = {
        row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(conversations)")
    }
    assert columns == {
        "id",
        "created_at",
        "updated_at",
        "turn_count",
        "subject",
        "agent_id",
        "user_profile_json",
        "message_history_json",
    }

    created = await repo.create_new()
    loaded = await repo.get(created.id)
    assert loaded is not None
    assert loaded.user_profile.interaction_count == 0
