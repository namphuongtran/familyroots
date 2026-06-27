"""Unit tests for infrastructure — event dispatcher and Unit of Work."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.shared.entity import AggregateRoot
from app.domain.shared.events import AuditableEvent, DomainEvent
from app.infrastructure.event_dispatcher import (
    AuditLogHandler,
    InMemoryEventDispatcher,
)
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

# ── InMemoryEventDispatcher ─────────────────────────────────────


class TestInMemoryEventDispatcher:
    @pytest.mark.asyncio
    async def test_dispatches_to_registered_handler(self) -> None:
        """Registered handler is called with the matching event."""
        dispatcher = InMemoryEventDispatcher()
        handler = AsyncMock()
        dispatcher.register(DomainEvent, handler)

        event = DomainEvent()
        await dispatcher.dispatch([event])

        handler.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_dispatches_to_parent_type_handler(self) -> None:
        """Handler for parent type receives child type events."""
        dispatcher = InMemoryEventDispatcher()
        handler = AsyncMock()
        dispatcher.register(DomainEvent, handler)

        # AuditableEvent inherits from DomainEvent
        event = AuditableEvent(action="test.action")
        await dispatcher.dispatch([event])

        handler.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_no_handler_registered(self) -> None:
        """Dispatching with no handlers does not raise."""
        dispatcher = InMemoryEventDispatcher()
        await dispatcher.dispatch([DomainEvent()])  # Should not raise

    @pytest.mark.asyncio
    async def test_multiple_handlers(self) -> None:
        """Multiple handlers for the same event are all called."""
        dispatcher = InMemoryEventDispatcher()
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        dispatcher.register(DomainEvent, handler1)
        dispatcher.register(DomainEvent, handler2)

        event = DomainEvent()
        await dispatcher.dispatch([event])

        handler1.assert_awaited_once_with(event)
        handler2.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_dispatch_reraises_handler_failure(self) -> None:
        """A failing handler must propagate so the UoW aborts the commit."""
        dispatcher = InMemoryEventDispatcher()

        async def boom(_event):
            raise RuntimeError("audit write failed")

        dispatcher.register(DomainEvent, boom)

        with pytest.raises(RuntimeError, match="audit write failed"):
            await dispatcher.dispatch([DomainEvent()])


# ── AuditLogHandler ─────────────────────────────────────────────


class TestAuditLogHandler:
    @pytest.mark.asyncio
    async def test_creates_audit_log_for_auditable_event(self) -> None:
        """AuditLogHandler creates an AuditLog row from AuditableEvent."""
        mock_db = MagicMock()
        handler = AuditLogHandler(mock_db)

        event = AuditableEvent(
            clan_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            actor_role="editor",
            action="person.create",
            resource_type="person",
            resource_id=uuid.uuid4(),
        )
        await handler.handle(event)

        mock_db.add.assert_called_once()
        audit_log = mock_db.add.call_args[0][0]
        assert audit_log.action == "person.create"
        assert audit_log.actor_role == "editor"

    @pytest.mark.asyncio
    async def test_ignores_non_auditable_event(self) -> None:
        """AuditLogHandler skips events that are not AuditableEvent."""
        mock_db = MagicMock()
        handler = AuditLogHandler(mock_db)

        await handler.handle(DomainEvent())

        mock_db.add.assert_not_called()


# ── SqlAlchemyUnitOfWork ────────────────────────────────────────


class TestSqlAlchemyUnitOfWork:
    @pytest.mark.asyncio
    async def test_commit_dispatches_events(self) -> None:
        """Commit collects events from tracked aggregates and dispatches them."""
        mock_session = AsyncMock()
        mock_dispatcher = AsyncMock()

        uow = SqlAlchemyUnitOfWork(mock_session, mock_dispatcher)

        agg = AggregateRoot()
        event = DomainEvent()
        agg.add_event(event)
        uow.track(agg)

        await uow.commit()

        mock_session.flush.assert_awaited_once()
        mock_dispatcher.dispatch.assert_awaited_once()
        dispatched_events = mock_dispatcher.dispatch.call_args[0][0]
        assert len(dispatched_events) == 1
        assert dispatched_events[0] is event
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commit_clears_tracked_aggregates(self) -> None:
        """After commit, tracked aggregates are cleared."""
        mock_session = AsyncMock()
        mock_dispatcher = AsyncMock()

        uow = SqlAlchemyUnitOfWork(mock_session, mock_dispatcher)
        agg = AggregateRoot()
        agg.add_event(DomainEvent())
        uow.track(agg)

        await uow.commit()

        # Second commit should not dispatch any events
        mock_dispatcher.dispatch.reset_mock()
        await uow.commit()
        mock_dispatcher.dispatch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_commit_without_events_skips_dispatch(self) -> None:
        """Commit with no tracked aggregates skips dispatching."""
        mock_session = AsyncMock()
        mock_dispatcher = AsyncMock()

        uow = SqlAlchemyUnitOfWork(mock_session, mock_dispatcher)
        await uow.commit()

        mock_dispatcher.dispatch.assert_not_awaited()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rollback_clears_aggregates(self) -> None:
        """Rollback clears tracked aggregates and calls session rollback."""
        mock_session = AsyncMock()
        mock_dispatcher = AsyncMock()

        uow = SqlAlchemyUnitOfWork(mock_session, mock_dispatcher)
        agg = AggregateRoot()
        agg.add_event(DomainEvent())
        uow.track(agg)

        await uow.rollback()

        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_track_deduplicates(self) -> None:
        """Tracking the same aggregate twice does not duplicate it."""
        mock_session = AsyncMock()
        mock_dispatcher = AsyncMock()

        uow = SqlAlchemyUnitOfWork(mock_session, mock_dispatcher)
        agg = AggregateRoot()
        event = DomainEvent()
        agg.add_event(event)
        uow.track(agg)
        uow.track(agg)  # duplicate

        await uow.commit()

        dispatched_events = mock_dispatcher.dispatch.call_args[0][0]
        assert len(dispatched_events) == 1  # not 2
