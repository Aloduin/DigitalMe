from datetime import UTC, datetime

from digitalme.ingestion.chatgpt.adapter import adapt_conversation


def test_adapter_preserves_conversation_tree_nodes() -> None:
    conversation = {
        "id": "conversation-1",
        "title": "A branched conversation",
        "create_time": 1_700_000_000,
        "update_time": 1_700_000_100,
        "current_node": "assistant-1",
        "mapping": {
            "root": {"id": "root", "parent": None, "message": None},
            "user-1": {
                "id": "user-1",
                "parent": "root",
                "message": {
                    "author": {"role": "user"},
                    "create_time": 1_700_000_001,
                    "content": {"content_type": "text", "parts": ["Hello"]},
                },
            },
            "assistant-1": {
                "id": "assistant-1",
                "parent": "user-1",
                "message": {
                    "author": {"role": "assistant"},
                    "create_time": 1_700_000_002,
                    "content": {
                        "content_type": "text",
                        "parts": ["Hi", {"text": "How can I help?"}, {"image": "ignored"}],
                    },
                },
            },
            "alternate": {
                "id": "alternate",
                "parent": "user-1",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["Alternate"]},
                },
            },
        },
    }

    session = adapt_conversation(
        conversation,
        member_name="conversations.json",
        conversation_index=0,
    )

    assert session.external_id == "conversation-1"
    assert session.selected_branch_head_external_id == "assistant-1"
    assert session.source_created_at == datetime.fromtimestamp(1_700_000_000, tz=UTC)
    assert [message.external_id for message in session.messages] == [
        "root",
        "user-1",
        "assistant-1",
        "alternate",
    ]
    assert session.messages[0].content_type == "empty_node"
    assert session.messages[2].parent_external_id == "user-1"
    assert session.messages[2].normalized_text == "Hi\nHow can I help?"
    assert session.messages[2].parse_warnings[0].code == "unsupported_content_parts"
