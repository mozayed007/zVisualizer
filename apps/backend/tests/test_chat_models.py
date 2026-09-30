from __future__ import annotations

from app.models.chat import ChatRequest, ConversationRecord, UserProfile


def test_chat_request_accepts_current_profile_key() -> None:
    request = ChatRequest.model_validate(
        {
            "message": "  explain raft  ",
            "user_profile": {
                "topics_visualized": ["paxos"],
                "unclear_topics": ["quorum"],
                "interaction_count": 3,
            },
        }
    )

    assert request.message == "explain raft"
    assert request.user_profile == UserProfile(
        topics_visualized=["paxos"],
        unclear_topics=["quorum"],
        interaction_count=3,
    )


def test_user_profile_serializes_field_names() -> None:
    profile = UserProfile(topics_visualized=["paxos"], unclear_topics=["quorum"], interaction_count=1)

    assert profile.model_dump() == {
        "topics_visualized": ["paxos"],
        "unclear_topics": ["quorum"],
        "interaction_count": 1,
    }


def test_conversation_record_defaults_to_empty_user_profile() -> None:
    record = ConversationRecord(id="conv_test")

    assert record.user_profile.interaction_count == 0
    assert record.user_profile.topics_visualized == []
