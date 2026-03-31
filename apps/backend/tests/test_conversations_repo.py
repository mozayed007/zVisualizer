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
