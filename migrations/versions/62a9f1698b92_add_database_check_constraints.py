"""Add database check constraints

Revision ID: 62a9f1698b92
Revises: 41088368f6c9
Create Date: 2026-11-07 17:15:10.279441

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '62a9f1698b92'
down_revision = '41088368f6c9'
branch_labels = None
depends_on = None

def upgrade():

    # PG table constraints
    with op.batch_alter_table("pg") as batch_op:
        batch_op.create_check_constraint(
            "check_pg_total_rooms",
            "total_rooms >= 0"
        )

        batch_op.create_check_constraint(
            "check_pg_available_rooms",
            "available_rooms >= 0"
        )

        batch_op.create_check_constraint(
            "check_pg_available_rooms_limit",
            "available_rooms <= total_rooms"
        )

    # Review table constraints
    with op.batch_alter_table("review") as batch_op:
        batch_op.create_check_constraint(
            "check_review_rating",
            "rating BETWEEN 1 AND 5"
        )

        batch_op.create_check_constraint(
            "check_review_cleanliness",
            "cleanliness IS NULL OR cleanliness BETWEEN 1 AND 5"
        )

        batch_op.create_check_constraint(
            "check_review_safety",
            "safety IS NULL OR safety BETWEEN 1 AND 5"
        )

        batch_op.create_check_constraint(
            "check_review_location",
            "location_rating IS NULL OR location_rating BETWEEN 1 AND 5"
        )

        batch_op.create_check_constraint(
            "check_review_facilities",
            "facilities_rating IS NULL OR facilities_rating BETWEEN 1 AND 5"
        )

    # Food subscription payment constraints
    with op.batch_alter_table("food_subscription_payment_request") as batch_op:
        batch_op.create_check_constraint(
            "check_payment_amount",
            "amount > 0"
        )

        batch_op.create_check_constraint(
            "check_payment_status",
            "status IN ('pending', 'approved', 'rejected')"
        )


def downgrade():

    # Remove PG constraints
    with op.batch_alter_table("pg") as batch_op:
        batch_op.drop_constraint(
            "check_pg_available_rooms_limit",
            type_="check"
        )

        batch_op.drop_constraint(
            "check_pg_available_rooms",
            type_="check"
        )

        batch_op.drop_constraint(
            "check_pg_total_rooms",
            type_="check"
        )

    # Remove Review constraints
    with op.batch_alter_table("review") as batch_op:
        batch_op.drop_constraint(
            "check_review_facilities",
            type_="check"
        )

        batch_op.drop_constraint(
            "check_review_location",
            type_="check"
        )

        batch_op.drop_constraint(
            "check_review_safety",
            type_="check"
        )

        batch_op.drop_constraint(
            "check_review_cleanliness",
            type_="check"
        )

        batch_op.drop_constraint(
            "check_review_rating",
            type_="check"
        )

    # Remove payment constraints
    with op.batch_alter_table("food_subscription_payment_request") as batch_op:
        batch_op.drop_constraint(
            "check_payment_status",
            type_="check"
        )

        batch_op.drop_constraint(
            "check_payment_amount",
            type_="check"
        )
