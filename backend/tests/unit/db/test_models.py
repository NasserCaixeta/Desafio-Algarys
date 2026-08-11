from clinic_confirmations.db.models import Appointment


def test_models_define_required_tables_and_unique_constraints() -> None:
    metadata = Appointment.metadata

    assert set(metadata.tables) == {
        "appointments",
        "confirmation_messages",
        "message_attempts",
    }
    appointment_constraints = {
        constraint.name for constraint in metadata.tables["appointments"].constraints
    }
    message_constraints = {
        constraint.name for constraint in metadata.tables["confirmation_messages"].constraints
    }
    attempt_constraints = {
        constraint.name for constraint in metadata.tables["message_attempts"].constraints
    }

    assert "uq_appointments_import_fingerprint" in appointment_constraints
    assert "uq_confirmation_messages_appointment_id" in message_constraints
    assert "uq_message_attempts_message_number" in attempt_constraints
    assert "ck_confirmation_messages_attempt_count_non_negative" in message_constraints


def test_models_define_operational_indexes() -> None:
    metadata = Appointment.metadata

    index_names = {index.name for table in metadata.tables.values() for index in table.indexes}
    assert {
        "ix_appointments_scheduled_at",
        "ix_appointments_status_scheduled_at",
        "ix_confirmation_messages_status_next_enqueue",
        "ix_confirmation_messages_processing_started_at",
    }.issubset(index_names)


def test_database_enums_use_public_lowercase_values() -> None:
    metadata = Appointment.metadata

    assert metadata.tables["appointments"].c.status.type.enums == [
        "pending",
        "confirmed",
        "declined",
    ]
    assert metadata.tables["confirmation_messages"].c.status.type.enums == [
        "pending",
        "processing",
        "sent",
        "failed",
    ]
