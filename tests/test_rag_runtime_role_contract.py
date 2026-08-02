from scripts.day6_provision_runtime import (
    KNOWLEDGE_COLUMN_READS,
    KNOWLEDGE_READ_TABLES,
)


def test_rag_runtime_role_has_only_required_read_contract() -> None:
    assert set(KNOWLEDGE_READ_TABLES) == {
        "kb_documents",
        "kb_chunks",
        "kb_document_versions",
        "kb_releases",
        "kb_release_items",
    }
    assert KNOWLEDGE_COLUMN_READS == {
        "kb_rag_audit_events": (
            "tenant_id",
            "release_id",
            "event_type",
            "details_json",
            "created_at",
        )
    }
    assert "actor_id" not in KNOWLEDGE_COLUMN_READS["kb_rag_audit_events"]
    assert "trace_id" not in KNOWLEDGE_COLUMN_READS["kb_rag_audit_events"]
