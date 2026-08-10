from importlib import import_module
from importlib.util import find_spec


def load_model_metadata():  # type: ignore[no-untyped-def]
    db_spec = find_spec("clinic_confirmations.db")
    assert db_spec is not None, "db package must exist"
    models_spec = find_spec("clinic_confirmations.db.models")
    assert models_spec is not None, "db.models package must exist"
    import_module("clinic_confirmations.db.models")
    return import_module("clinic_confirmations.db.base").Base.metadata


def test_models_define_required_tables_and_unique_constraints() -> None:
    metadata = load_model_metadata()

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
    metadata = load_model_metadata()

    index_names = {index.name for table in metadata.tables.values() for index in table.indexes}
    assert {
        "ix_appointments_scheduled_at",
        "ix_appointments_status_scheduled_at",
        "ix_confirmation_messages_status_next_enqueue",
        "ix_confirmation_messages_processing_started_at",
    }.issubset(index_names)


def test_database_enums_use_public_lowercase_values() -> None:
    metadata = load_model_metadata()

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
