from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "0018_rag_enterprise_r1.py"


def _assignment(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing assignment: {name}")


def test_rag_r1_revision_extends_day7a_linear_head():
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    assert _assignment(tree, "revision") == "0018_rag_enterprise_r1"
    assert _assignment(tree, "down_revision") == "0017_day6_operational"


def test_rag_r1_revision_covers_required_enterprise_tables_and_tenant_scope():
    source = MIGRATION.read_text(encoding="utf-8")
    for table in (
        "kb_documents",
        "kb_document_versions",
        "kb_chunks",
        "kb_assets",
        "kb_access_policies",
        "kb_releases",
        "kb_release_items",
        "kb_retrieval_runs",
        "kb_citations",
        "kb_qa_evaluations",
        "kb_rag_audit_events",
        "kb_search_results",
        "kb_qa_tests",
        "audit_logs",
    ):
        assert f'"{table}"' in source
    assert source.count('"tenant_id"') >= 45
    assert "embedding_dimension = 1024" in source
    assert "uq_kb_releases_current_tenant_r1" in source


def test_rag_r1_revision_freezes_terminal_and_release_states():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "terminal_status IN ('published','isolated','duplicate','damaged')" in source
    assert "status IN ('candidate','validated','published','superseded','rolled_back','failed')" in source
    assert "NOT is_current OR status = 'published'" in source


def test_rag_r1_revision_has_real_downgrade_without_seed_or_public_qualification():
    source = MIGRATION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "upgrade" in functions and "downgrade" in functions
    assert len(functions["downgrade"].body) > 3
    assert "INSERT INTO" not in source.upper()
    assert "public." not in source
    assert "DROP DATABASE" not in source.upper()
    assert "TRUNCATE" not in source.upper()


def test_rag_r1_revision_keeps_legacy_content_compatible():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "server_default=sa.text(\"'default'\")" in source
    assert 'sa.Column("version_id", sa.String(128), nullable=True)' in source
    assert "op.drop_table(\"kb_documents\")" not in source
    assert "op.drop_table(\"kb_chunks\")" not in source
