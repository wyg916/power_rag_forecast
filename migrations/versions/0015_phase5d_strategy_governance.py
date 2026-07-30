"""add PHASE5-D strategy governance and immutable review trail

Revision ID: 0015_phase5d_strategy
Revises: 0014_t003_run_transaction
Create Date: 2026-07-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0015_phase5d_strategy"
down_revision = "0014_t003_run_transaction"
branch_labels = None
depends_on = None


_STRATEGY_COLUMNS = (
    sa.Column("strategy_id", sa.String(96), nullable=True),
    sa.Column("strategy_version", sa.Integer(), nullable=True, server_default="1"),
    sa.Column("report_id", sa.String(96), nullable=True),
    sa.Column("model_version", sa.String(128), nullable=True),
    sa.Column("feature_version", sa.String(128), nullable=True),
    sa.Column("domain", sa.String(64), nullable=True, server_default="strategy"),
    sa.Column("target_name", sa.String(128), nullable=True),
    sa.Column("strategy_type", sa.String(64), nullable=True),
    sa.Column("title", sa.String(255), nullable=True),
    sa.Column("summary", sa.Text(), nullable=True),
    sa.Column("status", sa.String(32), nullable=True, server_default="draft"),
    sa.Column("priority", sa.Integer(), nullable=True, server_default="0"),
    sa.Column("confidence", sa.Float(), nullable=True),
    sa.Column("source_type", sa.String(32), nullable=True),
    sa.Column("is_stale", sa.Boolean(), nullable=True, server_default=sa.false()),
    sa.Column("stale_reason", sa.String(128), nullable=True),
    sa.Column("applicable_start_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("applicable_end_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    sa.Column("created_by", sa.String(128), nullable=True),
    sa.Column("rule_version", sa.String(64), nullable=True),
    sa.Column("prompt_version", sa.String(64), nullable=True),
    sa.Column("model_provider", sa.String(64), nullable=True),
    sa.Column("model_name", sa.String(128), nullable=True),
    sa.Column("constraints_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("expected_effect_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("prohibited_actions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("review_required", sa.Boolean(), nullable=True, server_default=sa.true()),
    sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("approved_by", sa.String(128), nullable=True),
    sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("rejected_by", sa.String(128), nullable=True),
    sa.Column("rejection_reason", sa.Text(), nullable=True),
    sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("published_by", sa.String(128), nullable=True),
    sa.Column("supersedes_strategy_id", sa.String(96), nullable=True),
    sa.Column("content_hash", sa.String(64), nullable=True),
)


def _columns(table: str) -> set[str]:
    return {str(item["name"]) for item in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {str(item["name"]) for item in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    existing = _columns("strategy_advice")
    for column in _STRATEGY_COLUMNS:
        if column.name not in existing:
            op.add_column("strategy_advice", column)

    op.execute("UPDATE strategy_advice SET strategy_id = 'legacy_' || id::text WHERE strategy_id IS NULL")
    op.execute("UPDATE strategy_advice SET status = 'draft' WHERE status IS NULL")
    op.execute("UPDATE strategy_advice SET strategy_version = 1 WHERE strategy_version IS NULL")
    op.alter_column("strategy_advice", "strategy_id", existing_type=sa.String(96), nullable=False)
    op.alter_column("strategy_advice", "status", existing_type=sa.String(32), nullable=False)
    op.alter_column("strategy_advice", "strategy_version", existing_type=sa.Integer(), nullable=False)

    indexes = _indexes("strategy_advice")
    if "uq_strategy_advice_strategy_id_p5d" not in indexes:
        op.create_index("uq_strategy_advice_strategy_id_p5d", "strategy_advice", ["strategy_id"], unique=True)
    if "uq_strategy_advice_content_hash_p5d" not in indexes:
        op.create_index("uq_strategy_advice_content_hash_p5d", "strategy_advice", ["content_hash"], unique=True,
                        postgresql_where=sa.text("content_hash IS NOT NULL"))
    if "idx_strategy_advice_lookup_p5d" not in indexes:
        op.create_index("idx_strategy_advice_lookup_p5d", "strategy_advice", ["run_id", "report_id", "status"])

    op.execute(
        """
        ALTER TABLE strategy_advice
        ADD CONSTRAINT ck_strategy_advice_status_p5d
        CHECK (status IN ('draft','pending_review','approved','rejected','published','superseded','expired','cancelled'))
        """
    )
    op.create_table(
        "strategy_reviews",
        sa.Column("review_id", sa.String(96), primary_key=True),
        sa.Column("strategy_id", sa.String(96), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("previous_status", sa.String(32), nullable=False),
        sa.Column("new_status", sa.String(32), nullable=False),
        sa.Column("reviewer", sa.String(128), nullable=False),
        sa.Column("reviewer_role", sa.String(64), nullable=False),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("evidence_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("strategy_content_hash", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategy_advice.strategy_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("request_id", name="uq_strategy_reviews_request_id_p5d"),
        sa.CheckConstraint(
            "action IN ('submit','approve','reject','return','publish','supersede','expire','cancel')",
            name="ck_strategy_reviews_action_p5d",
        ),
    )
    op.create_index("idx_strategy_reviews_history_p5d", "strategy_reviews", ["strategy_id", "created_at"])
    op.execute(
        """INSERT INTO roles (role_id,role_name,permissions_json,description,created_at,updated_at)
        VALUES ('reviewer','策略审核员','[\"strategy:read\",\"strategy:review\"]'::jsonb,
                '可读取并人工审核策略，不可生成、提交或发布策略',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        ON CONFLICT (role_id) DO NOTHING"""
    )



def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("strategy_reviews"):
        op.drop_table("strategy_reviews")
    indexes = _indexes("strategy_advice")
    for name in ("idx_strategy_advice_lookup_p5d", "uq_strategy_advice_content_hash_p5d", "uq_strategy_advice_strategy_id_p5d"):
        if name in indexes:
            op.drop_index(name, table_name="strategy_advice")
    constraints = {item.get("name") for item in sa.inspect(op.get_bind()).get_check_constraints("strategy_advice")}
    if "ck_strategy_advice_status_p5d" in constraints:
        op.drop_constraint("ck_strategy_advice_status_p5d", "strategy_advice", type_="check")
    existing = _columns("strategy_advice")
    for column in reversed(_STRATEGY_COLUMNS):
        if column.name in existing:
            op.drop_column("strategy_advice", column.name)
