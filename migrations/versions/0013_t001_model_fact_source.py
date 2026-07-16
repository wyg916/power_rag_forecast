"""add T001 model fact identity and unique-active constraints

Revision ID: 0013_t001_model_fact
Revises: 0012_backend_legacy_tables
Create Date: 2026-07-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op


revision = "0013_t001_model_fact"
down_revision = "0012_backend_legacy_tables"
branch_labels = None
depends_on = None


_COLUMNS = (
    sa.Column("model_id", sa.String(length=128), nullable=True),
    sa.Column("domain", sa.String(length=64), nullable=True),
    sa.Column("target_name", sa.String(length=128), nullable=True),
    sa.Column("artifact_id", sa.String(length=128), nullable=True),
    sa.Column("artifact_hash", sa.String(length=128), nullable=True),
    sa.Column("schema_hash", sa.String(length=128), nullable=True),
    sa.Column("validated_at", sa.DateTime(), nullable=True),
    sa.Column("deactivated_at", sa.DateTime(), nullable=True),
    sa.Column("source_type", sa.String(length=32), nullable=True),
)


def _columns() -> set[str]:
    return {str(item["name"]) for item in sa.inspect(op.get_bind()).get_columns("model_registry")}


def _indexes() -> set[str]:
    return {str(item["name"]) for item in sa.inspect(op.get_bind()).get_indexes("model_registry")}


def _offline_mode() -> bool:
    try:
        return bool(context.is_offline_mode())
    except NameError:
        # Direct migration unit tests install an Operations proxy without an
        # Alembic EnvironmentContext; that is an online, real-connection path.
        return False


def upgrade() -> None:
    offline = _offline_mode()
    existing_columns = set() if offline else _columns()
    for column in _COLUMNS:
        if column.name not in existing_columns:
            op.add_column("model_registry", column)

    if offline:
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM model_registry
                    WHERE domain IS NOT NULL AND target_name IS NOT NULL
                      AND LOWER(status) = 'active' AND is_active = 1
                    GROUP BY domain, target_name
                    HAVING COUNT(*) > 1
                ) THEN
                    RAISE EXCEPTION 'duplicate active model facts for domain and target_name';
                END IF;
            END $$
            """
        )
        duplicate = None
    else:
        duplicate = op.get_bind().execute(
            sa.text(
                """
                SELECT domain, target_name, COUNT(*) AS active_count
                FROM model_registry
                WHERE domain IS NOT NULL AND target_name IS NOT NULL
                  AND LOWER(status) = 'active' AND is_active = 1
                GROUP BY domain, target_name
                HAVING COUNT(*) > 1
                LIMIT 1
                """
            )
        ).first()
    if duplicate:
        raise RuntimeError("检测到同一 domain+target_name 存在多个 Active；迁移拒绝自动修改历史数据")

    existing_indexes = set() if offline else _indexes()
    if "uq_model_registry_model_id" not in existing_indexes:
        op.create_index(
            "uq_model_registry_model_id",
            "model_registry",
            ["model_id"],
            unique=True,
            postgresql_where=sa.text("model_id IS NOT NULL"),
            sqlite_where=sa.text("model_id IS NOT NULL"),
        )
    if "uq_model_registry_active_domain_target" not in existing_indexes:
        predicate = sa.text("domain IS NOT NULL AND target_name IS NOT NULL AND LOWER(status) = 'active' AND is_active = 1")
        op.create_index(
            "uq_model_registry_active_domain_target",
            "model_registry",
            ["domain", "target_name"],
            unique=True,
            postgresql_where=predicate,
            sqlite_where=predicate,
        )


def downgrade() -> None:
    # Non-destructive downgrade: remove enforcement indexes but retain nullable
    # identity/lifecycle columns so rollback never discards model history.
    existing_indexes = (
        {"uq_model_registry_active_domain_target", "uq_model_registry_model_id"}
        if _offline_mode()
        else _indexes()
    )
    if "uq_model_registry_active_domain_target" in existing_indexes:
        op.drop_index("uq_model_registry_active_domain_target", table_name="model_registry")
    if "uq_model_registry_model_id" in existing_indexes:
        op.drop_index("uq_model_registry_model_id", table_name="model_registry")
