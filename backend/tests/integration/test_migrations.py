import os

from sqlalchemy import create_engine, inspect

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://clinic:clinic_local_password@localhost:5433/clinic_confirmations_test",
)


def test_initial_migration_creates_domain_tables_and_indexes() -> None:
    engine = create_engine(TEST_DATABASE_URL)
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == {
            "alembic_version",
            "appointments",
            "confirmation_messages",
            "message_attempts",
        }
        assert "ix_appointments_status_scheduled_at" in {
            index["name"] for index in inspector.get_indexes("appointments")
        }
        assert "ix_confirmation_messages_status_next_enqueue" in {
            index["name"] for index in inspector.get_indexes("confirmation_messages")
        }
        assert {
            "ck_confirmation_messages_attempt_count_non_negative",
            "ck_confirmation_messages_enqueue_attempts_non_negative",
            "ck_confirmation_messages_max_attempts_positive",
        } == {
            constraint["name"]
            for constraint in inspector.get_check_constraints("confirmation_messages")
        }
    finally:
        engine.dispose()
