from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from clinic_confirmations.core.config import Settings
from clinic_confirmations.db.models import Appointment, ConfirmationMessage, MessageAttempt
from clinic_confirmations.domain.enums import AttemptResult, MessageStatus
from clinic_confirmations.domain.errors import RetryLimitReachedError, RetryNotAllowedError
from clinic_confirmations.repositories.messages import MessageRepository
from clinic_confirmations.sender.simulated import SimulatedSender
from clinic_confirmations.services.message_processing import process_message
from clinic_confirmations.services.retry import (
    recover_stale_processing,
    schedule_due_retries,
    schedule_manual_retry,
)


def test_manual_retry_reuses_message_and_makes_it_due(
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    now = datetime(2026, 8, 11, 12, tzinfo=UTC)
    message = message_factory(
        status=MessageStatus.FAILED,
        attempt_count=1,
        last_error="simulated failure",
        next_enqueue_at=now + timedelta(minutes=5),
    )
    original_id = message.id

    result = schedule_manual_retry(db_session, original_id, now=now)

    db_session.refresh(message)
    assert result.id == original_id
    assert message.id == original_id
    assert message.status == MessageStatus.PENDING
    assert message.attempt_count == 1
    assert message.last_error == "simulated failure"
    assert message.enqueued_at is None
    assert message.next_enqueue_at == now


def test_retry_limit_is_rejected(
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    message = message_factory(
        status=MessageStatus.FAILED,
        attempt_count=3,
        max_attempts=3,
    )

    with pytest.raises(RetryLimitReachedError):
        schedule_manual_retry(db_session, message.id, now=datetime.now(UTC))


def test_retry_is_rejected_for_non_failed_message(
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    message = message_factory(status=MessageStatus.SENT, attempt_count=1)

    with pytest.raises(RetryNotAllowedError):
        schedule_manual_retry(db_session, message.id, now=datetime.now(UTC))


def test_due_failures_are_scheduled_automatically(
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    now = datetime(2026, 8, 11, 12, tzinfo=UTC)
    due = message_factory(
        status=MessageStatus.FAILED,
        attempt_count=1,
        next_enqueue_at=now - timedelta(seconds=1),
    )
    future = message_factory(
        status=MessageStatus.FAILED,
        attempt_count=1,
        next_enqueue_at=now + timedelta(seconds=1),
    )
    exhausted = message_factory(
        status=MessageStatus.FAILED,
        attempt_count=3,
        max_attempts=3,
        next_enqueue_at=now - timedelta(seconds=1),
    )

    count = schedule_due_retries(db_session, now=now, batch_size=10)

    assert count == 1
    db_session.refresh(due)
    db_session.refresh(future)
    db_session.refresh(exhausted)
    assert due.status == MessageStatus.PENDING
    assert due.next_enqueue_at == now
    assert future.status == MessageStatus.FAILED
    assert exhausted.status == MessageStatus.FAILED


def test_stale_lease_is_abandoned_and_old_token_cannot_finish(
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    now = datetime(2026, 8, 11, 12, tzinfo=UTC)
    token = uuid4()
    message = message_factory(
        status=MessageStatus.PROCESSING,
        attempt_count=1,
        processing_token=token,
        processing_started_at=now - timedelta(seconds=61),
        enqueued_at=now - timedelta(seconds=70),
    )
    attempt = MessageAttempt(
        message_id=message.id,
        attempt_number=1,
        processing_token=token,
        started_at=now - timedelta(seconds=61),
    )
    db_session.add(attempt)
    db_session.flush()

    recovered = recover_stale_processing(
        db_session,
        now=now,
        lease_seconds=60,
        batch_size=10,
    )
    old_worker_finished = MessageRepository(db_session).finalize_success(
        message.id,
        token,
        now=now + timedelta(seconds=1),
    )

    db_session.refresh(message)
    db_session.refresh(attempt)
    assert recovered == 1
    assert message.status == MessageStatus.PENDING
    assert message.processing_token is None
    assert message.enqueued_at is None
    assert message.next_enqueue_at == now
    assert attempt.result == AttemptResult.ABANDONED
    assert attempt.completed_at == now
    assert old_worker_finished is False


def test_fresh_processing_lease_is_not_recovered(
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    now = datetime(2026, 8, 11, 12, tzinfo=UTC)
    message = message_factory(
        status=MessageStatus.PROCESSING,
        attempt_count=1,
        processing_token=uuid4(),
        processing_started_at=now - timedelta(seconds=59),
    )

    recovered = recover_stale_processing(
        db_session,
        now=now,
        lease_seconds=60,
        batch_size=10,
    )

    assert recovered == 0
    db_session.refresh(message)
    assert message.status == MessageStatus.PROCESSING


def test_automatic_retry_succeeds_on_second_attempt_using_same_message(
    db_session: Session,
    appointment_factory: Callable[..., Appointment],
    message_factory: Callable[..., ConfirmationMessage],
    test_settings: Settings,
) -> None:
    appointment = appointment_factory(phone="+5534999990000")
    message = message_factory(
        appointment=appointment,
        enqueued_at=datetime.now(UTC),
    )
    original_id = message.id
    factory = sessionmaker(bind=db_session.connection(), expire_on_commit=False)
    sender = SimulatedSender(("0000",), failure_attempts=1, latency_ms=0)

    first = process_message(factory, sender, message.id, test_settings)
    db_session.refresh(message)
    assert first.status == MessageStatus.FAILED
    assert message.next_enqueue_at is not None
    retry_at = message.next_enqueue_at

    assert schedule_due_retries(db_session, now=retry_at, batch_size=10) == 1
    second = process_message(
        factory,
        sender,
        message.id,
        test_settings,
        now=retry_at,
    )

    db_session.refresh(message)
    attempts = db_session.scalars(
        select(MessageAttempt)
        .where(MessageAttempt.message_id == message.id)
        .order_by(MessageAttempt.attempt_number)
    ).all()
    assert second.status == MessageStatus.SENT
    assert message.id == original_id
    assert message.status == MessageStatus.SENT
    assert message.attempt_count == 2
    assert [attempt.result for attempt in attempts] == [
        AttemptResult.FAILED,
        AttemptResult.SENT,
    ]


def test_stale_final_attempt_stays_failed_without_another_retry(
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    now = datetime(2026, 8, 11, 12, tzinfo=UTC)
    token = uuid4()
    message = message_factory(
        status=MessageStatus.PROCESSING,
        attempt_count=3,
        max_attempts=3,
        processing_token=token,
        processing_started_at=now - timedelta(seconds=61),
    )
    attempt = MessageAttempt(
        message_id=message.id,
        attempt_number=3,
        processing_token=token,
        started_at=now - timedelta(seconds=61),
    )
    db_session.add(attempt)
    db_session.flush()

    recovered = recover_stale_processing(
        db_session,
        now=now,
        lease_seconds=60,
        batch_size=10,
    )

    db_session.refresh(message)
    db_session.refresh(attempt)
    assert recovered == 1
    assert message.status == MessageStatus.FAILED
    assert message.next_enqueue_at is None
    assert message.attempt_count == 3
    assert attempt.result == AttemptResult.ABANDONED
