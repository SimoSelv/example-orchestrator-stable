"""Add Check Node Health task.

Revision ID: 72413ade14ea
Revises: a87d11eb8dd1
Create Date: 2026-04-28 00:45:00.000000

"""
#simona
import sqlalchemy as sa
from alembic import op
from orchestrator.migrations.helpers import delete_workflow
from orchestrator.targets import Target

# revision identifiers, used by Alembic.
revision = "72413ade14ea"
down_revision = "a87d11eb8dd1"
branch_labels = None
depends_on = None

tasks = [
    {
        "name": "task_check_node_health",
        "target": Target.SYSTEM,
        "description": "Check Node Health",
        "is_task": True,
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    for task in tasks:
        conn.execute(
            sa.text(
                """INSERT INTO workflows(name, target, description, is_task) VALUES (:name, :target, :description, :is_task)
                   ON CONFLICT DO NOTHING"""
            ),
            task,
        )


def downgrade() -> None:
    conn = op.get_bind()
    for task in tasks:
        delete_workflow(conn, task["name"])
