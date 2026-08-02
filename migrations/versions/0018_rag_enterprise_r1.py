"""add RAG-R1 enterprise persistence and release governance

Revision ID: 0018_rag_enterprise_r1
Revises: 0017_day6_operational
Create Date: 2026-08-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0018_rag_enterprise_r1"
down_revision = "0017_day6_operational"
branch_labels = None
depends_on = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def _columns(table: str) -> set[str]:
    return {str(item["name"]) for item in sa.inspect(op.get_bind()).get_columns(table)}


def _constraints(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    names = {
        str(item["name"])
        for item in inspector.get_foreign_keys(table)
        if item.get("name")
    }
    names.update(
        str(item["name"])
        for item in inspector.get_unique_constraints(table)
        if item.get("name")
    )
    names.update(
        str(item["name"])
        for item in inspector.get_check_constraints(table)
        if item.get("name")
    )
    return names


def _indexes(table: str) -> set[str]:
    return {
        str(item["name"])
        for item in sa.inspect(op.get_bind()).get_indexes(table)
        if item.get("name")
    }


def _add_column(table: str, column: sa.Column[object]) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _drop_column(table: str, name: str) -> None:
    if name in _columns(table):
        op.drop_column(table, name)


def upgrade() -> None:
    _add_column(
        "kb_documents",
        sa.Column(
            "tenant_id",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'default'"),
        ),
    )
    _add_column("kb_documents", sa.Column("domain", sa.String(96), nullable=True))
    _add_column(
        "kb_documents", sa.Column("owner_actor_id", sa.String(128), nullable=True)
    )
    if "uq_kb_documents_tenant_doc_r1" not in _constraints("kb_documents"):
        op.create_unique_constraint(
            "uq_kb_documents_tenant_doc_r1",
            "kb_documents",
            ["tenant_id", "doc_id"],
        )
    op.create_index(
        "idx_kb_documents_tenant_updated_r1",
        "kb_documents",
        ["tenant_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "kb_document_versions",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("version_id", sa.String(128), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("declared_format", sa.String(32), nullable=False),
        sa.Column("detected_format", sa.String(32), nullable=False),
        sa.Column("parser_profile", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("parse_status", sa.String(32), nullable=False),
        sa.Column("isolation_reason", sa.String(128), nullable=True),
        sa.Column("duplicate_of_version_id", sa.String(128), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "version_id", name="pk_kb_document_versions_r1"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["kb_documents.tenant_id", "kb_documents.doc_id"],
            name="fk_kb_document_versions_document_r1",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "source_sha256",
            name="uq_kb_document_versions_source_r1",
        ),
        sa.CheckConstraint(
            "parse_status IN ('ready','isolated','duplicate','damaged')",
            name="ck_kb_document_versions_status_r1",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from",
            name="ck_kb_document_versions_effective_r1",
        ),
    )
    op.create_index(
        "idx_kb_document_versions_source_r1",
        "kb_document_versions",
        ["tenant_id", "source_id", "parse_status"],
    )
    op.create_index(
        "idx_kb_document_versions_hash_r1",
        "kb_document_versions",
        ["tenant_id", "content_sha256"],
    )

    for column in (
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default=sa.text("'default'")),
        sa.Column("version_id", sa.String(128), nullable=True),
        sa.Column("parent_chunk_id", sa.String(128), nullable=True),
        sa.Column("chunk_level", sa.String(16), nullable=False, server_default=sa.text("'child'")),
        sa.Column("section_path_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("locator_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_sha256", sa.String(64), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding_provider", sa.String(64), nullable=True),
        sa.Column("embedding_model", sa.String(128), nullable=True),
        sa.Column("embedding_version", sa.String(128), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("embedding_status", sa.String(32), nullable=True),
    ):
        _add_column("kb_chunks", column)
    if "uq_kb_chunks_tenant_chunk_r1" not in _constraints("kb_chunks"):
        op.create_unique_constraint(
            "uq_kb_chunks_tenant_chunk_r1",
            "kb_chunks",
            ["tenant_id", "chunk_id"],
        )
    if "fk_kb_chunks_version_r1" not in _constraints("kb_chunks"):
        op.create_foreign_key(
            "fk_kb_chunks_version_r1",
            "kb_chunks",
            "kb_document_versions",
            ["tenant_id", "version_id"],
            ["tenant_id", "version_id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "idx_kb_chunks_version_parent_r1",
        "kb_chunks",
        ["tenant_id", "version_id", "parent_chunk_id"],
    )
    op.create_index(
        "idx_kb_chunks_content_hash_r1",
        "kb_chunks",
        ["tenant_id", "content_sha256"],
    )

    op.create_table(
        "kb_assets",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("asset_id", sa.String(128), nullable=False),
        sa.Column("version_id", sa.String(128), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("bbox_json", JSONB, nullable=True),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("ocr_profile", sa.String(128), nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("quality_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "asset_id", name="pk_kb_assets_r1"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["kb_document_versions.tenant_id", "kb_document_versions.version_id"],
            name="fk_kb_assets_version_r1",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "idx_kb_assets_version_page_r1",
        "kb_assets",
        ["tenant_id", "version_id", "page_number"],
    )

    op.create_table(
        "kb_access_policies",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("policy_id", sa.String(128), nullable=False),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("effect", sa.String(8), nullable=False),
        sa.Column("permissions_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "policy_id", name="pk_kb_access_policies_r1"),
        sa.CheckConstraint("subject_type IN ('role','user')", name="ck_kb_access_policies_subject_r1"),
        sa.CheckConstraint("effect IN ('allow','deny')", name="ck_kb_access_policies_effect_r1"),
    )
    op.create_index(
        "idx_kb_access_policies_subject_r1",
        "kb_access_policies",
        ["tenant_id", "subject_type", "subject_id", "resource_type"],
    )

    op.create_table(
        "kb_releases",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("release_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("collection_name", sa.String(255), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("source_ledger_sha256", sa.String(64), nullable=False),
        sa.Column("embedding_provider", sa.String(64), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("embedding_version", sa.String(128), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("embedding_model_sha256", sa.String(64), nullable=False),
        sa.Column("reranker_model", sa.String(128), nullable=False),
        sa.Column("reranker_version", sa.String(128), nullable=False),
        sa.Column("reranker_model_sha256", sa.String(64), nullable=False),
        sa.Column("sparse_profile", sa.String(64), nullable=False),
        sa.Column("previous_release_id", sa.String(128), nullable=True),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "release_id", name="pk_kb_releases_r1"),
        sa.CheckConstraint(
            "status IN ('candidate','validated','published','superseded','rolled_back','failed')",
            name="ck_kb_releases_status_r1",
        ),
        sa.CheckConstraint(
            "embedding_dimension = 1024", name="ck_kb_releases_dimension_r1"
        ),
        sa.CheckConstraint(
            "NOT is_current OR status = 'published'",
            name="ck_kb_releases_current_status_r1",
        ),
    )
    op.create_index(
        "uq_kb_releases_current_tenant_r1",
        "kb_releases",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        "idx_kb_releases_status_created_r1",
        "kb_releases",
        ["tenant_id", "status", "created_at"],
    )

    op.create_table(
        "kb_release_items",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("release_id", sa.String(128), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=True),
        sa.Column("version_id", sa.String(128), nullable=True),
        sa.Column("terminal_status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(128), nullable=True),
        sa.Column("duplicate_of_source_id", sa.String(128), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("asset_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_sha256", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "item_id", name="pk_kb_release_items_r1"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "release_id"],
            ["kb_releases.tenant_id", "kb_releases.release_id"],
            name="fk_kb_release_items_release_r1",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["kb_document_versions.tenant_id", "kb_document_versions.version_id"],
            name="fk_kb_release_items_version_r1",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id", "release_id", "source_id", name="uq_kb_release_items_source_r1"
        ),
        sa.CheckConstraint(
            "terminal_status IN ('published','isolated','duplicate','damaged')",
            name="ck_kb_release_items_terminal_r1",
        ),
        sa.CheckConstraint("chunk_count >= 0 AND asset_count >= 0", name="ck_kb_release_items_counts_r1"),
    )
    op.create_index(
        "idx_kb_release_items_status_r1",
        "kb_release_items",
        ["tenant_id", "release_id", "terminal_status"],
    )

    op.create_table(
        "kb_retrieval_runs",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("retrieval_run_id", sa.String(128), nullable=False),
        sa.Column("release_id", sa.String(128), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("acl_fingerprint", sa.String(64), nullable=False),
        sa.Column("query_sha256", sa.String(64), nullable=False),
        sa.Column("filters_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("requested_top_k", sa.Integer(), nullable=False),
        sa.Column("returned_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("degraded_components_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("timings_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "retrieval_run_id", name="pk_kb_retrieval_runs_r1"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "release_id"],
            ["kb_releases.tenant_id", "kb_releases.release_id"],
            name="fk_kb_retrieval_runs_release_r1",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("requested_top_k > 0", name="ck_kb_retrieval_runs_top_k_r1"),
        sa.CheckConstraint("returned_count >= 0", name="ck_kb_retrieval_runs_count_r1"),
        sa.CheckConstraint(
            "status IN ('available','unavailable','error')",
            name="ck_kb_retrieval_runs_status_r1",
        ),
    )
    op.create_index(
        "idx_kb_retrieval_runs_trace_r1",
        "kb_retrieval_runs",
        ["tenant_id", "release_id", "trace_id", "created_at"],
    )

    op.create_table(
        "kb_citations",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("citation_id", sa.String(128), nullable=False),
        sa.Column("retrieval_run_id", sa.String(128), nullable=False),
        sa.Column("release_id", sa.String(128), nullable=False),
        sa.Column("claim_id", sa.String(128), nullable=False),
        sa.Column("version_id", sa.String(128), nullable=False),
        sa.Column("chunk_id", sa.String(96), nullable=False),
        sa.Column("locator_json", JSONB, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "citation_id", name="pk_kb_citations_r1"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "retrieval_run_id"],
            ["kb_retrieval_runs.tenant_id", "kb_retrieval_runs.retrieval_run_id"],
            name="fk_kb_citations_retrieval_r1",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "release_id"],
            ["kb_releases.tenant_id", "kb_releases.release_id"],
            name="fk_kb_citations_release_r1",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["kb_document_versions.tenant_id", "kb_document_versions.version_id"],
            name="fk_kb_citations_version_r1",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "chunk_id"],
            ["kb_chunks.tenant_id", "kb_chunks.chunk_id"],
            name="fk_kb_citations_chunk_r1",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "idx_kb_citations_claim_r1",
        "kb_citations",
        ["tenant_id", "retrieval_run_id", "claim_id"],
    )

    op.create_table(
        "kb_qa_evaluations",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("evaluation_id", sa.String(128), nullable=False),
        sa.Column("release_id", sa.String(128), nullable=False),
        sa.Column("retrieval_run_id", sa.String(128), nullable=True),
        sa.Column("suite_name", sa.String(128), nullable=False),
        sa.Column("question_id", sa.String(128), nullable=False),
        sa.Column("critical", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Numeric(8, 6), nullable=False),
        sa.Column("confidence_label", sa.String(32), nullable=True),
        sa.Column("metrics_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("citation_ids_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "evaluation_id", name="pk_kb_qa_evaluations_r1"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "release_id"],
            ["kb_releases.tenant_id", "kb_releases.release_id"],
            name="fk_kb_qa_evaluations_release_r1",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "retrieval_run_id"],
            ["kb_retrieval_runs.tenant_id", "kb_retrieval_runs.retrieval_run_id"],
            name="fk_kb_qa_evaluations_retrieval_r1",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_kb_qa_evaluations_confidence_r1"),
    )
    op.create_index(
        "idx_kb_qa_evaluations_suite_r1",
        "kb_qa_evaluations",
        ["tenant_id", "release_id", "suite_name", "passed"],
    )

    op.create_table(
        "kb_rag_audit_events",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("release_id", sa.String(128), nullable=True),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("details_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "event_id", name="pk_kb_rag_audit_events_r1"),
    )
    op.create_index(
        "idx_kb_rag_audit_events_trace_r1",
        "kb_rag_audit_events",
        ["tenant_id", "trace_id", "created_at"],
    )
    op.create_index(
        "idx_kb_rag_audit_events_release_r1",
        "kb_rag_audit_events",
        ["tenant_id", "release_id", "created_at"],
    )

    for table, columns in {
        "kb_search_results": (
            sa.Column("tenant_id", sa.String(64), nullable=False, server_default=sa.text("'default'")),
            sa.Column("release_id", sa.String(128), nullable=True),
            sa.Column("run_id", sa.String(128), nullable=True),
            sa.Column("trace_id", sa.String(128), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'unavailable'")),
            sa.Column("citations_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        ),
        "kb_qa_tests": (
            sa.Column("tenant_id", sa.String(64), nullable=False, server_default=sa.text("'default'")),
            sa.Column("release_id", sa.String(128), nullable=True),
            sa.Column("run_id", sa.String(128), nullable=True),
            sa.Column("trace_id", sa.String(128), nullable=True),
            sa.Column("grounding_status", sa.String(32), nullable=True),
            sa.Column("citations_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("confidence_label", sa.String(32), nullable=True),
        ),
        "audit_logs": (
            sa.Column("tenant_id", sa.String(64), nullable=False, server_default=sa.text("'default'")),
            sa.Column("release_id", sa.String(128), nullable=True),
            sa.Column("run_id", sa.String(128), nullable=True),
            sa.Column("trace_id", sa.String(128), nullable=True),
        ),
    }.items():
        for column in columns:
            _add_column(table, column)
    op.create_index(
        "idx_kb_search_results_release_trace_r1",
        "kb_search_results",
        ["tenant_id", "release_id", "trace_id", "created_at"],
    )
    op.create_index(
        "idx_kb_qa_tests_release_run_r1",
        "kb_qa_tests",
        ["tenant_id", "release_id", "run_id", "created_at"],
    )
    op.create_index(
        "idx_audit_logs_tenant_trace_r1",
        "audit_logs",
        ["tenant_id", "trace_id", "created_at"],
    )


def downgrade() -> None:
    for table, index in (
        ("audit_logs", "idx_audit_logs_tenant_trace_r1"),
        ("kb_qa_tests", "idx_kb_qa_tests_release_run_r1"),
        ("kb_search_results", "idx_kb_search_results_release_trace_r1"),
    ):
        if index in _indexes(table):
            op.drop_index(index, table_name=table)

    for table, names in {
        "audit_logs": ("trace_id", "run_id", "release_id", "tenant_id"),
        "kb_qa_tests": (
            "confidence_label",
            "citations_json",
            "grounding_status",
            "trace_id",
            "run_id",
            "release_id",
            "tenant_id",
        ),
        "kb_search_results": (
            "citations_json",
            "status",
            "trace_id",
            "run_id",
            "release_id",
            "tenant_id",
        ),
    }.items():
        for name in names:
            _drop_column(table, name)

    for table in (
        "kb_rag_audit_events",
        "kb_qa_evaluations",
        "kb_citations",
        "kb_retrieval_runs",
        "kb_release_items",
        "kb_releases",
        "kb_access_policies",
        "kb_assets",
    ):
        op.drop_table(table)

    if "fk_kb_chunks_version_r1" in _constraints("kb_chunks"):
        op.drop_constraint("fk_kb_chunks_version_r1", "kb_chunks", type_="foreignkey")
    for index in (
        "idx_kb_chunks_content_hash_r1",
        "idx_kb_chunks_version_parent_r1",
    ):
        if index in _indexes("kb_chunks"):
            op.drop_index(index, table_name="kb_chunks")
    if "uq_kb_chunks_tenant_chunk_r1" in _constraints("kb_chunks"):
        op.drop_constraint("uq_kb_chunks_tenant_chunk_r1", "kb_chunks", type_="unique")
    for name in (
        "embedding_status",
        "embedding_dimension",
        "embedding_version",
        "embedding_model",
        "embedding_provider",
        "token_count",
        "content_sha256",
        "locator_json",
        "section_path_json",
        "chunk_level",
        "parent_chunk_id",
        "version_id",
        "tenant_id",
    ):
        _drop_column("kb_chunks", name)

    op.drop_table("kb_document_versions")
    if "idx_kb_documents_tenant_updated_r1" in _indexes("kb_documents"):
        op.drop_index("idx_kb_documents_tenant_updated_r1", table_name="kb_documents")
    if "uq_kb_documents_tenant_doc_r1" in _constraints("kb_documents"):
        op.drop_constraint(
            "uq_kb_documents_tenant_doc_r1", "kb_documents", type_="unique"
        )
    for name in ("owner_actor_id", "domain", "tenant_id"):
        _drop_column("kb_documents", name)
