"""Initial migration

Revision ID: 001
Create Date: 2026-07-17 20:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.String(length=510), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("email_verification_token_hash", sa.String(length=128), nullable=True),
        sa.Column("email_verification_expires_at", sa.DateTime(), nullable=True),
        sa.Column("password_reset_token_hash", sa.String(length=128), nullable=True),
        sa.Column("password_reset_expires_at", sa.DateTime(), nullable=True),
        sa.Column("google_sub", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)

    op.create_table(
        "cafes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("roastery", sa.String(length=255), nullable=False),
        sa.Column("origin", sa.String(length=255), nullable=False),
        sa.Column("region", sa.String(length=255), nullable=True),
        sa.Column("variety", sa.String(length=255), nullable=True),
        sa.Column("process", sa.String(length=100), nullable=True),
        sa.Column("altitude", sa.String(length=100), nullable=True),
        sa.Column("roast_level", sa.String(length=100), nullable=True),
        sa.Column("roast_date", sa.Date(), nullable=True),
        sa.Column("sensory_notes", sa.Text(), nullable=True),
        sa.Column("sca_score", sa.Float(), nullable=True),
        sa.Column("photo_url", sa.String(length=510), nullable=True),
        sa.Column("is_favorite", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cafes_id"), "cafes", ["id"], unique=False)

    op.create_table(
        "beverages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_cold", sa.Boolean(), nullable=False),
        sa.Column("ingredients", sa.Text(), nullable=True),
        sa.Column("espresso_shots", sa.Integer(), nullable=False),
        sa.Column("total_volume_ml", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_beverages_id"), "beverages", ["id"], unique=False)
    op.create_index(op.f("ix_beverages_name"), "beverages", ["name"], unique=False)

    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("coffee_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("method", sa.String(length=100), nullable=False),
        sa.Column("coffee_weight", sa.Float(), nullable=False),
        sa.Column("water_weight", sa.Float(), nullable=False),
        sa.Column("grind_size", sa.String(length=100), nullable=True),
        sa.Column("water_temp", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("steps", sa.JSON(), nullable=True),
        sa.Column("is_favorite", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["coffee_id"], ["cafes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recipes_id"), "recipes", ["id"], unique=False)

    op.create_table(
        "stock",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coffee_id", sa.Integer(), nullable=False),
        sa.Column("current_quantity", sa.Float(), nullable=False),
        sa.Column("min_quantity", sa.Float(), nullable=False),
        sa.Column("is_opened", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["coffee_id"], ["cafes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("coffee_id"),
    )
    op.create_index(op.f("ix_stock_id"), "stock", ["id"], unique=False)

    op.create_table(
        "extractions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=True),
        sa.Column("coffee_id", sa.Integer(), nullable=True),
        sa.Column("total_time", sa.Integer(), nullable=False),
        sa.Column("extraction_date", sa.DateTime(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["coffee_id"], ["cafes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_extractions_id"), "extractions", ["id"], unique=False)

    op.create_table(
        "sensory_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("coffee_id", sa.Integer(), nullable=True),
        sa.Column("extraction_id", sa.Integer(), nullable=True),
        sa.Column("aroma_score", sa.Integer(), nullable=False),
        sa.Column("acidity_score", sa.Integer(), nullable=False),
        sa.Column("body_score", sa.Integer(), nullable=False),
        sa.Column("sweetness_score", sa.Integer(), nullable=False),
        sa.Column("aftertaste_score", sa.Integer(), nullable=False),
        sa.Column("perceived_notes", sa.Text(), nullable=True),
        sa.Column("unperceived_notes", sa.Text(), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["coffee_id"], ["cafes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["extraction_id"], ["extractions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sensory_logs_id"), "sensory_logs", ["id"], unique=False)

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("quantity_changed", sa.Float(), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["stock_id"], ["stock.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stock_movements_id"), "stock_movements", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_stock_movements_id"), table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index(op.f("ix_sensory_logs_id"), table_name="sensory_logs")
    op.drop_table("sensory_logs")
    op.drop_index(op.f("ix_extractions_id"), table_name="extractions")
    op.drop_table("extractions")
    op.drop_index(op.f("ix_stock_id"), table_name="stock")
    op.drop_table("stock")
    op.drop_index(op.f("ix_recipes_id"), table_name="recipes")
    op.drop_table("recipes")
    op.drop_index(op.f("ix_beverages_name"), table_name="beverages")
    op.drop_index(op.f("ix_beverages_id"), table_name="beverages")
    op.drop_table("beverages")
    op.drop_index(op.f("ix_cafes_id"), table_name="cafes")
    op.drop_table("cafes")
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
