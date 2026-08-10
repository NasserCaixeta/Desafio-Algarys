from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from clinic_confirmations.core.config import Settings
from clinic_confirmations.db.models import ConfirmationMessage
from clinic_confirmations.queue.publisher import reconcile_enqueue


class CountingPublisher:
    def __init__(self) -> None:
        self.count = 0

    def send_task(
        self,
        name: str,
        args: list[object] | None = None,
        kwargs: dict[str, object] | None = None,
        queue: str | None = None,
    ) -> object:
        self.count += 1
        return object()


def test_reconciliation_republishes_only_unmarked_due_messages(
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
    test_settings: Settings,
) -> None:
    now = datetime(2026, 8, 11, 12, tzinfo=UTC)
    due = message_factory(next_enqueue_at=now - timedelta(seconds=1))
    future = message_factory(next_enqueue_at=now + timedelta(seconds=1))
    marked = message_factory(
        next_enqueue_at=now - timedelta(seconds=1),
        enqueued_at=now - timedelta(seconds=2),
    )
    publisher = CountingPublisher()

    first_count = reconcile_enqueue(
        db_session,
        publisher,
        test_settings,
        batch_size=10,
        now=now,
    )
    second_count = reconcile_enqueue(
        db_session,
        publisher,
        test_settings,
        batch_size=10,
        now=now,
    )

    assert first_count == 1
    assert second_count == 0
    db_session.refresh(due)
    db_session.refresh(future)
    db_session.refresh(marked)
    assert due.enqueued_at == now
    assert future.enqueued_at is None
    assert marked.enqueued_at is not None
    assert publisher.count == 1
