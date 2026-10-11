"""Permit executor-free links only for the explicit public readonly shape.

Revision ID: c8f041b2965e
Revises: 6aa7efd8cbc4
"""

import sqlalchemy as sa
from alembic import op

revision = "c8f041b2965e"
down_revision = "6aa7efd8cbc4"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("task_links", "executor", existing_type=sa.String(42), nullable=True)
    op.create_check_constraint(
        "public_readonly_executor",
        "task_links",
        "executor IS NOT NULL OR COALESCE(("
        "body->'task_link'->>'completion_kind' = 'readonly-query' AND "
        "body->'task_link'->>'capability_id' = 'verify_record' AND "
        "body->'task_link'->'executor' = 'null'::jsonb AND "
        "body->'task_link'->'candidate_tx_hash' = 'null'::jsonb AND "
        "body->'task_link'->'verified_tx_hash' = 'null'::jsonb AND "
        "body->'task_link'->'log_index' = 'null'::jsonb), false)",
    )
    op.create_index(
        "uq_task_links_public_request",
        "task_links",
        ["chain_instance_id", "request_id"],
        unique=True,
        postgresql_where=sa.text("executor IS NULL"),
    )


def downgrade():
    if op.get_bind().execute(
        sa.text("SELECT 1 FROM task_links WHERE executor IS NULL LIMIT 1")
    ).first() is not None:
        raise RuntimeError("Cannot downgrade while public readonly task links exist")
    op.alter_column("task_links", "executor", existing_type=sa.String(42), nullable=False)
    op.drop_index("uq_task_links_public_request", table_name="task_links")
    op.drop_constraint(op.f("ck_task_links_public_readonly_executor"), "task_links", type_="check")
