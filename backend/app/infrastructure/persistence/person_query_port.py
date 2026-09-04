"""SQLAlchemy implementation of the Person read operations.

Every read has a batch form (single ANY-style query for N persons) and the
single-person methods delegate to it with a one-element list — one SQL
implementation per concern, so /persons/batch stays O(1) queries per include
token instead of O(N) per person.

**An edge read carries two soft-delete predicates, not one** (ADR-051,
2026-08-22). ``Marriage.is_deleted`` / ``ParentChild.is_deleted`` says whether
someone deleted *the edge*. It says nothing about the persons the edge points
at, and nothing cascades a person's delete onto its edges — ``PersonDeleted``
has no consumer (``app/domain/person/entity.py:267-280``; whether a cascade
should exist at all is ADR-051's decision, and this filter stays correct
either way). So every edge read here also hides an edge with a soft-deleted
person on either end, which is what ``get_timelines_batch`` below and the tree
builder already did. Before this, ``GET /persons/{id}/marriages`` handed a
client an edge pointing at a person the same API answered ``404`` for.

**Write that predicate as ``NOT EXISTS``, not as a join, and the reason is
measured.** The obvious shape is the timeline's: join the counterpart person and
require ``is_deleted = false``. It is correct, and here it is slow, because these
are batch reads over a set of persons rather than one row. Measured 2026-08-22 on
PostgreSQL 18.4, against 20,000 persons / 10,000 marriages / 5,000 parent-child
rows loaded into the migrated test database. ``EXPLAIN (ANALYZE)`` of the
marriages batch read for 100 person ids, one run, all four in the same session:

* edge filter only, the behaviour before the fix — ``0.115 ms``
* **the statement this module now emits**, one ``NOT EXISTS`` over both
  endpoints — ``0.246 ms``: a Nested Loop Anti Join feeding
  ``Index Scan using pk_persons``, 50 loops at ~0.004 ms each
* two inner joins on ``persons`` — ``3.598 ms``: a Hash Join that
  **sequentially scans all 18,000 live persons twice** to build the hashes
* two correlated ``EXISTS``, one per endpoint — ``3.922 ms``: Postgres flattens
  a semi-join into that same hash join, so this buys nothing

Absolute times move by roughly 3x between runs on a laptop; the plans do not.
**That is the durable part**: the join's cost grows with the size of ``persons``,
and the anti-join's grows with the number of edges matched, which the read is
already paying for. ``get_stats_for_persons`` uses the same ``NOT EXISTS`` for
consistency, though there the choice does not change the plan — its subqueries
are correlated to one ``p.id``, so every form stayed an index-driven nested loop
(``0.367`` / ``0.611`` / ``0.758 ms`` for the three shapes, inside the noise).
The timeline keeps its join because it needs the spouse's **name**, so it has to
visit the person row either way.

**The anti-join asks "is a deleted person on this edge", which is also the
safer question under RLS.** A soft delete does not touch ``clan_memberships``,
so the deleted person's row stays visible to ``persons_sel`` (membership-keyed,
migration ``029``) and the anti-join sees it and hides the edge. An inner join
would additionally drop an edge whose counterpart the request role cannot see at
all — a non-member — which migration ``029``'s load-bearing invariant says
cannot happen, so the two agree today on every reachable row.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.person.query_port import PersonQueryPort
from app.models.clan_membership import ClanMembership
from app.models.document import Document
from app.models.event import Event
from app.models.marriage import Marriage
from app.models.parent_child import ParentChild
from app.models.person import Person
from app.schemas.document import DocumentSummary
from app.schemas.event import EventResponse, TimelineEvent
from app.schemas.historical_date import to_historical_date
from app.schemas.marriage import MarriageResponse
from app.schemas.parent_child import ParentChildResponse
from app.services.translator import t


def _empty_map(person_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict[str, Any]]]:
    return {pid: [] for pid in person_ids}


def _no_deleted_endpoint(*endpoint_ids: ColumnElement[uuid.UUID]) -> ColumnElement[bool]:
    """``NOT EXISTS (SELECT 1 FROM persons WHERE id IN (…) AND is_deleted)``.

    The second half of every edge predicate in this module — see the module
    docstring for why it is an anti-join rather than a join.

    Also imported by ``relationship_repository.py``, where the two by-id read
    ports carry the same predicate (2026-08-22). It stays private
    because nothing outside ``app.infrastructure.persistence`` may use it, and
    it stays one definition because two copies of a visibility rule drift.
    """
    return ~(
        select(1)
        .select_from(Person)
        .where(Person.id.in_(endpoint_ids), Person.is_deleted.is_(True))
        .exists()
    )


class SqlAlchemyPersonQueryPort(PersonQueryPort):
    """SQLAlchemy implementation of PersonQueryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── marriages ────────────────────────────────────────────────────────

    async def get_marriages_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        out = _empty_map(person_ids)
        if not person_ids:
            return out
        # Both spouses must be live, not only the marriage row — see the module
        # docstring, including why this is an anti-join and not a join.
        result = await self._session.execute(
            select(Marriage).where(
                or_(Marriage.person1_id.in_(person_ids), Marriage.person2_id.in_(person_ids)),
                Marriage.created_by_clan_id == clan_id,
                Marriage.is_deleted.is_(False),
                _no_deleted_endpoint(Marriage.person1_id, Marriage.person2_id),
            )
        )
        for m in result.scalars().all():
            dumped = MarriageResponse.model_validate(m).model_dump()
            for pid in (m.person1_id, m.person2_id):
                if pid in out:
                    out[pid].append(dumped)
        return out

    async def get_marriages(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        return (await self.get_marriages_batch(clan_id, [person_id]))[person_id]

    # ── parent-child links ───────────────────────────────────────────────

    async def get_parent_child_links_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        out = _empty_map(person_ids)
        if not person_ids:
            return out
        # Both ends of the lineage edge must be live — see the module docstring.
        result = await self._session.execute(
            select(ParentChild).where(
                or_(ParentChild.parent_id.in_(person_ids), ParentChild.child_id.in_(person_ids)),
                ParentChild.created_by_clan_id == clan_id,
                ParentChild.is_deleted.is_(False),
                _no_deleted_endpoint(ParentChild.parent_id, ParentChild.child_id),
            )
        )
        for link in result.scalars().all():
            dumped = ParentChildResponse.model_validate(link).model_dump()
            for pid in (link.parent_id, link.child_id):
                if pid in out:
                    out[pid].append(dumped)
        return out

    async def get_parent_child_links(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        return (await self.get_parent_child_links_batch(clan_id, [person_id]))[person_id]

    # ── documents ────────────────────────────────────────────────────────

    async def get_documents_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        out = _empty_map(person_ids)
        if not person_ids:
            return out
        result = await self._session.execute(
            select(Document).where(
                Document.clan_id == clan_id,
                Document.person_id.in_(person_ids),
                Document.is_deleted.is_(False),
            )
        )
        for d in result.scalars().all():
            if d.person_id in out:
                out[d.person_id].append(DocumentSummary.model_validate(d).model_dump())
        return out

    async def get_documents(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        return (await self.get_documents_batch(clan_id, [person_id]))[person_id]

    # ── events ───────────────────────────────────────────────────────────

    async def get_events_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        out = _empty_map(person_ids)
        if not person_ids:
            return out
        for ev in await self._event_rows(clan_id, person_ids):
            if ev.person_id in out:
                out[ev.person_id].append(EventResponse.model_validate(ev).model_dump())
        return out

    async def get_events(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        return (await self.get_events_batch(clan_id, [person_id]))[person_id]

    async def _event_rows(self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]) -> list[Event]:
        result = await self._session.execute(
            select(Event).where(
                Event.clan_id == clan_id,
                Event.person_id.in_(person_ids),
                Event.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    # ── timeline ─────────────────────────────────────────────────────────

    async def get_timelines_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        """Chronological timelines (birth/death, marriages, events) for N
        persons in exactly three queries."""
        out = _empty_map(person_ids)
        if not person_ids:
            return out

        # 1. Persons — scoped to the caller's clan (via membership) and
        # excluding soft-deleted, so the timeline is self-contained rather
        # than relying on the route's prior clan check.
        person_result = await self._session.execute(
            select(Person)
            .join(ClanMembership, ClanMembership.person_id == Person.id)
            .where(
                Person.id.in_(person_ids),
                ClanMembership.clan_id == clan_id,
                Person.is_deleted.is_(False),
            )
        )
        for person in person_result.scalars().all():
            if person.birth_date:
                out[person.id].append(
                    TimelineEvent(
                        event_date=to_historical_date(
                            person.birth_date,
                            person.birth_date_precision,
                            person.birth_date_display,
                            person.lunar_birth_date,
                        ),
                        event_type="birth",
                        title=t("timeline.birth"),
                    ).model_dump()
                )
            if person.death_date:
                out[person.id].append(
                    TimelineEvent(
                        event_date=to_historical_date(
                            person.death_date,
                            person.death_date_precision,
                            person.death_date_display,
                            person.lunar_death_date,
                        ),
                        event_type="death",
                        title=t("timeline.death"),
                    ).model_dump()
                )

        # 2. Marriages — clan-scoped; a soft-deleted spouse must not surface.
        p1 = aliased(Person)
        p2 = aliased(Person)
        spouse_result = await self._session.execute(
            select(
                Marriage.person1_id,
                Marriage.person2_id,
                Marriage.marriage_date,
                Marriage.marriage_date_precision,
                Marriage.marriage_date_display,
                p1.full_name.label("p1_name"),
                p1.is_deleted.label("p1_deleted"),
                p2.full_name.label("p2_name"),
                p2.is_deleted.label("p2_deleted"),
            )
            .join(p1, p1.id == Marriage.person1_id)
            .join(p2, p2.id == Marriage.person2_id)
            .where(
                or_(Marriage.person1_id.in_(person_ids), Marriage.person2_id.in_(person_ids)),
                Marriage.created_by_clan_id == clan_id,
                Marriage.is_deleted.is_(False),
            )
        )
        for row in spouse_result.mappings().all():
            if not row["marriage_date"]:
                continue
            sides = (
                (row["person1_id"], row["person2_id"], row["p2_name"], row["p2_deleted"]),
                (row["person2_id"], row["person1_id"], row["p1_name"], row["p1_deleted"]),
            )
            for pid, spouse_id, spouse_name, spouse_deleted in sides:
                if pid not in out or spouse_deleted:
                    continue
                out[pid].append(
                    TimelineEvent(
                        event_date=to_historical_date(
                            row["marriage_date"],
                            row["marriage_date_precision"],
                            row["marriage_date_display"],
                            None,
                        ),
                        event_type="marriage",
                        title=t("timeline.marriage"),
                        related_person_id=spouse_id,
                        related_person_name=spouse_name,
                    ).model_dump()
                )

        # 3. Lifecycle events.
        for ev in await self._event_rows(clan_id, person_ids):
            if ev.person_id in out:
                out[ev.person_id].append(
                    TimelineEvent(
                        event_date=to_historical_date(
                            ev.event_date, ev.event_date_precision, ev.event_date_display, None
                        ),
                        event_type=ev.event_type,
                        title=ev.title,
                        description=ev.description,
                    ).model_dump()
                )

        for timeline in out.values():
            timeline.sort(key=lambda e: (e.get("event_date") or {}).get("date") or date.max)
        return out

    async def get_timeline(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        """Build a chronological timeline from birth/death, marriages, and events."""
        return (await self.get_timelines_batch(clan_id, [person_id]))[person_id]
