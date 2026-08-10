"""Create appointments, confirmation messages and attempts.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

appointment_status = postgresql.ENUM(
    "pending",
    "confirmed",
    "declined",
    name="appointment_status",
    create_type=False,
)
message_status = postgresql.ENUM(
    "pending",
    "processing",
    "sent",
    "failed",
    name="message_status",
    create_type=False,
)
attempt_result = postgresql.ENUM(
    "processing",
    "sent",
    "failed",
    "abandoned",
    name="attempt_result",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    appointment_status.create(bind, checkfirst=True)
    message_status.create(bind, checkfirst=True)
    attempt_result.create(bind, checkfirst=True)

    op.create_table(
        "appointments",
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("patient_name", sa.String(length=160), nullable=False),
        sa.Column("phone", sa.String(length=16), nullable=False),
        sa.Column("procedure", sa.String(length=200), nullable=False),
        sa.Column("status", appointment_status, server_default="pending", nullable=False),
        sa.Column("import_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_appointments"),
        sa.UniqueConstraint("import_fingerprint", name="uq_appointments_import_fingerprint"),
    )
    op.create_index("ix_appointments_scheduled_at", "appointments", ["scheduled_at"])
    op.create_index(
        "ix_appointments_status_scheduled_at",
        "appointments",
        ["status", "scheduled_at"],
    )

    op.create_table(
        "confirmation_messages",
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("status", message_status, server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enqueue_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_enqueue_error", sa.Text(), nullable=True),
        sa.Column("next_enqueue_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_token", sa.Uuid(), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_confirmation_messages_attempt_count_non_negative"),
        ),
        sa.CheckConstraint(
            "enqueue_attempts >= 0",
            name=op.f("ck_confirmation_messages_enqueue_attempts_non_negative"),
        ),
        sa.CheckConstraint(
            "max_attempts > 0",
            name=op.f("ck_confirmation_messages_max_attempts_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"],
            ["appointments.id"],
            name="fk_confirmation_messages_appointment_id_appointments",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_confirmation_messages"),
        sa.UniqueConstraint("appointment_id", name="uq_confirmation_messages_appointment_id"),
    )
    op.create_index(
        "ix_confirmation_messages_processing_started_at",
        "confirmation_messages",
        ["processing_started_at"],
    )
    op.create_index(
        "ix_confirmation_messages_status_next_enqueue",
        "confirmation_messages",
        ["status", "next_enqueue_at"],
    )

    op.create_table(
        "message_attempts",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("processing_token", sa.Uuid(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", attempt_result, server_default="processing", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["confirmation_messages.id"],
            name="fk_message_attempts_message_id_confirmation_messages",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_message_attempts"),
        sa.UniqueConstraint(
            "message_id",
            "attempt_number",
            name="uq_message_attempts_message_number",
        ),
    )


def downgrade() -> None:
    op.drop_table("message_attempts")
    op.drop_index(
        "ix_confirmation_messages_status_next_enqueue", table_name="confirmation_messages"
    )
    op.drop_index(
        "ix_confirmation_messages_processing_started_at", table_name="confirmation_messages"
    )
    op.drop_table("confirmation_messages")
    op.drop_index("ix_appointments_status_scheduled_at", table_name="appointments")
    op.drop_index("ix_appointments_scheduled_at", table_name="appointments")
    op.drop_table("appointments")

    bind = op.get_bind()
    attempt_result.drop(bind, checkfirst=True)
    message_status.drop(bind, checkfirst=True)
    appointment_status.drop(bind, checkfirst=True)
