"""SQLAlchemy implementation of EventRepository.

Encapsulates all Event persistence including the complex upcoming-events
query with recurring logic (optimized as a CTE).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select, text
from sqlalchemy import update as sql_update

from app.domain.event.entity import Event as EventEntity
from app.domain.shared.exceptions import ConflictError
from app.infrastructure.persistence.event_mapper import MAPPED_FIELDS, to_domain, to_orm
from app.infrastructure.persistence.sql_dates import next_anniversary_sql
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.models.clan_membership import ClanMembership
from app.models.event import Event as EventModel
from app.models.person import Person as PersonModel
from app.schemas.historical_date import to_historical_date
from app.services.lunar_calendar import next_lunar_anniversary

logger = logging.getLogger(__name__)


class SqlAlchemyEventRepository:
    """Concrete Event repository backed by SQLAlchemy + PostgreSQL."""

    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow
        self._session = uow.session

    async def get_by_id(
        self, event_id: uuid.UUID, clan_id: uuid.UUID, include_deleted: bool = False
    ) -> EventEntity | None:
        stmt = select(EventModel).where(EventModel.id == event_id, EventModel.clan_id == clan_id)
        if not include_deleted:
            stmt = stmt.where(EventModel.is_deleted.is_(False))
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return to_domain(model) if model else None

    async def person_in_clan(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> bool:
        """A soft-deleted person is invisible here, matching the read paths
        (M3, review 2026-07-18)."""
        result = await self._session.execute(
            select(ClanMembership.person_id)
            .join(PersonModel, PersonModel.id == ClanMembership.person_id)
            .where(
                ClanMembership.person_id == person_id,
                ClanMembership.clan_id == clan_id,
                PersonModel.is_deleted.is_(False),
            )
        )
        return result.first() is not None

    async def list_in_clan(
        self,
        clan_id: uuid.UUID,
        *,
        person_id: uuid.UUID | None = None,
        event_type: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[EventEntity]:
        from app.core.pagination import paginate_query

        query = select(EventModel).where(
            EventModel.clan_id == clan_id, EventModel.is_deleted.is_(False)
        )
        if person_id:
            query = query.where(EventModel.person_id == person_id)
        if event_type:
            query = query.where(EventModel.event_type == event_type)

        query = paginate_query(query, EventModel, cursor, limit)
        result = await self._session.execute(query)
        return [to_domain(m) for m in result.scalars().all()]

    async def get_upcoming(
        self,
        clan_id: uuid.UUID,
        *,
        today: date,
        end_date: date,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Upcoming events with recurring logic — optimized CTE.

        Mirrors scheduler.py's filter — /upcoming shows exactly what will be
        notified: a soft-deleted person's events are invisible here too
        (M3, review 2026-07-18)."""
        this_year = next_anniversary_sql("EXTRACT(YEAR FROM :today)", "e.event_date")
        next_year = next_anniversary_sql("EXTRACT(YEAR FROM :today) + 1", "e.event_date")
        result = await self._session.execute(
            text(f"""
                WITH next_dates AS (
                    SELECT
                        e.id, e.person_id, e.event_type, e.title,
                        e.event_date, e.event_date_precision, e.event_date_display,
                        e.is_lunar_calendar, e.is_recurring,
                        p.full_name AS person_name,
                        p.avatar_url AS person_avatar_url,
                        CASE
                            WHEN e.is_recurring THEN
                                CASE
                                    WHEN {this_year} >= :today THEN {this_year}
                                    ELSE {next_year}
                                END
                            ELSE e.event_date
                        END AS next_occurrence
                    FROM public.events e
                    LEFT JOIN public.persons p ON p.id = e.person_id
                    WHERE e.clan_id = :clan_id
                        AND e.is_deleted = false
                        AND (e.is_recurring = true OR e.event_date >= :today)
                        AND NOT (e.is_recurring = true AND e.is_lunar_calendar = true)
                        AND (e.person_id IS NULL OR p.is_deleted = false)
                )
                SELECT * FROM next_dates
                WHERE next_occurrence BETWEEN :today AND :end_date
                ORDER BY next_occurrence ASC
                LIMIT :lim
            """),
            {"clan_id": clan_id, "today": today, "end_date": end_date, "lim": limit},
        )
        rows = result.mappings().all()

        # Lunar recurring events cannot be expressed as a solar-date-arithmetic CTE
        # (see next_anniversary_sql) — the anniversary must go through the VN lunar
        # conversion engine. Query them separately, compute next_occurrence in
        # Python, then merge with the solar rows before sorting/limiting.
        lunar_result = await self._session.execute(
            text("""
                SELECT e.id, e.person_id, e.event_type, e.title,
                       e.event_date, e.event_date_precision, e.event_date_display,
                       e.is_lunar_calendar, e.is_recurring,
                       p.full_name AS person_name,
                       p.avatar_url AS person_avatar_url
                FROM public.events e
                LEFT JOIN public.persons p ON p.id = e.person_id
                WHERE e.clan_id = :clan_id
                  AND e.is_deleted = false
                  AND e.is_recurring = true
                  AND e.is_lunar_calendar = true
                  AND (e.person_id IS NULL OR p.is_deleted = false)
            """),
            {"clan_id": clan_id},
        )
        lunar_rows: list[dict[str, Any]] = []
        for lunar_row in lunar_result.mappings().all():
            try:
                occ = next_lunar_anniversary(lunar_row["event_date"], today)
            except ValueError:
                # A pathological event_date (e.g. outside the lunar engine's
                # supported year range, Finding 1) must not 500 the whole
                # /events/upcoming response — skip just this row.
                logger.warning(
                    "Skipping lunar event %s in get_upcoming: event_date=%s "
                    "cannot be converted by the lunar engine",
                    lunar_row["id"],
                    lunar_row["event_date"],
                    exc_info=True,
                )
                continue
            if today <= occ <= end_date:
                lunar_rows.append({**lunar_row, "next_occurrence": occ})

        merged: list[dict[str, Any]] = [dict(r) for r in rows]
        merged.extend(lunar_rows)
        all_rows = sorted(merged, key=lambda r: r["next_occurrence"])[:limit]

        upcoming = []
        for row in all_rows:
            next_occ = row["next_occurrence"]
            upcoming.append(
                {
                    "id": str(row["id"]),
                    "person_id": str(row["person_id"]) if row["person_id"] else None,
                    "person_name": row["person_name"],
                    "person_avatar_url": row["person_avatar_url"],
                    "event_type": row["event_type"],
                    "title": row["title"],
                    # event_date is the recorded HistoricalDate (precision/display carried
                    # from the events table; events have no lunar column, so lunar=None).
                    "event_date": to_historical_date(
                        row["event_date"],
                        row["event_date_precision"],
                        row["event_date_display"],
                        None,
                    ).model_dump(),
                    # next_occurrence is a DERIVED recurrence date (computed anniversary),
                    # not a recorded historical date — stays a scalar ISO string.
                    "next_occurrence": next_occ.isoformat() if next_occ else None,
                    "days_until": (next_occ - today).days if next_occ else None,
                    "is_lunar_calendar": row["is_lunar_calendar"],
                }
            )
        return upcoming

    async def save(self, event: EventEntity, *, expected_version: int | None = None) -> None:
        """Insert, or update with an optimistic-concurrency check (ADR-022).

        expected_version=None (delete/restore paths) updates unconditionally
        but still bumps version so any concurrent PATCH sees a stale_write —
        the same contract persons/marriages use (ADR-017).
        """
        self._uow.track(event)
        existing = await self._session.get(EventModel, event.id)
        if existing is None:
            self._session.add(to_orm(event))
            return

        values = {f: getattr(event, f) for f in MAPPED_FIELDS}
        values["updated_at"] = event.updated_at
        stmt = (
            sql_update(EventModel)
            .where(EventModel.id == event.id)
            .values(**values, version=EventModel.version + 1)
        )
        if expected_version is not None:
            stmt = stmt.where(EventModel.version == expected_version)
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            current = await self._session.scalar(
                select(EventModel.version).where(EventModel.id == event.id)
            )
            raise ConflictError("stale_write", detail={"current_version": current})
        await self._session.refresh(existing)  # sync identity map with the core UPDATE
        event.version = existing.version
