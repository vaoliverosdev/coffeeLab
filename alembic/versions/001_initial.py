"""Initial migration

Revision ID: 001
Create Date: 2026-07-17 20:00:00.000000
"""

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Schema base; as tabelas virão nas migrações das próximas fases
    pass


def downgrade() -> None:
    pass