from pathlib import Path

from scripts.rag_r1_migration_readiness import migration_readiness, read_revision_graph


def test_current_migration_graph_is_static_linear_and_not_reserved():
    result = migration_readiness()
    assert result["inspection_mode"] == "static_ast_only"
    assert result["database_connected"] is False
    assert result["revision_created"] is False
    assert result["linear"] is True
    assert result["current_heads"] == ["0017_day6_operational"]
    assert result["planned_down_revision"] == "0017_day6_operational"
    assert result["planned_revision"] is None
    assert "rag_r1_revision_not_created" in result["blockers"]
    assert "migration_execution_confirmation_required" in result["blockers"]
    assert "kb_document_versions" in result["new_tables"]
    assert "kb_documents" in result["extended_tables"]


def test_revision_graph_rejects_fork(tmp_path: Path):
    (tmp_path / "0001.py").write_text(
        'revision = "0001"\ndown_revision = None\n', encoding="utf-8"
    )
    (tmp_path / "0002_a.py").write_text(
        'revision = "0002_a"\ndown_revision = "0001"\n', encoding="utf-8"
    )
    (tmp_path / "0002_b.py").write_text(
        'revision = "0002_b"\ndown_revision = "0001"\n', encoding="utf-8"
    )
    assert len(read_revision_graph(tmp_path)) == 3
    result = migration_readiness(tmp_path)
    assert result["linear"] is False
    assert result["planned_down_revision"] is None
    assert "alembic_graph_not_linear" in result["blockers"]
