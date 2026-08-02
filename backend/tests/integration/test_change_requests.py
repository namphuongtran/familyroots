"""Change-request workflow end-to-end over real Postgres (ADR-037, ADR-016).

Real migrations, real RBAC (``require_role`` queries ``user_clan_roles``), real
Person aggregate + repository + UoW. Only JWT *verification* is stubbed — the bearer
token IS the user id — following ``test_occ_persons.py``, so these tests exercise the
change-request contract rather than re-proving auth.

The headline is ``TestStaleness``: a proposal sits while somebody else edits the same
person, and the outcome is the designed three-way merge, proven rather than hoped
for. ``TestNegativeControl`` proves that suite would actually catch a regression.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import RlsSession, get_db
from app.core.rls import set_request_clan_id
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

CR = "/api/v1/change-requests"


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Test-only stub: the bearer token IS the user id (no signature verification)."""
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


async def _seed_clan(
    session_factory: async_sessionmaker[AsyncSession], label: str
) -> dict[str, Any]:
    """A clan with one approved viewer, editor and admin."""
    clan_id = uuid.uuid4()
    users = {role: uuid.uuid4() for role in ("viewer", "editor", "admin")}
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": clan_id, "name": f"CR Clan {label}", "slug": f"cr-{clan_id.hex[:8]}"},
        )
        for role, uid in users.items():
            await s.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name) "
                    "VALUES (:id, :email, :name)"
                ),
                {"id": uid, "email": f"{uid.hex[:8]}@example.com", "name": f"{label}-{role}"},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:uid, :cid, :role, true, :uid, now())"
                ),
                {"uid": uid, "cid": clan_id, "role": role},
            )
        await s.commit()
    return {"clan_id": clan_id, **{f"{role}_id": uid for role, uid in users.items()}}


@pytest.fixture()
async def clan_a(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    return await _seed_clan(session_factory, "A")


@pytest.fixture()
async def clan_b(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    return await _seed_clan(session_factory, "B")


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def _headers(seed: dict[str, Any], role: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seed[f'{role}_id']}",
        "X-Current-Clan-Id": str(seed["clan_id"]),
    }


@pytest.fixture()
def viewer(clan_a: dict[str, Any]) -> dict[str, str]:
    return _headers(clan_a, "viewer")


@pytest.fixture()
def editor(clan_a: dict[str, Any]) -> dict[str, str]:
    return _headers(clan_a, "editor")


@pytest.fixture()
def admin(clan_a: dict[str, Any]) -> dict[str, str]:
    return _headers(clan_a, "admin")


async def _create_person(
    client: AsyncClient, headers: dict[str, str], **overrides: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "full_name": "Cụ Nguyễn Văn Tổ",
        "gender": "male",
        "birth_date": "1919-01-01",
        "birth_place": "Hà Nội",
    }
    body.update(overrides)
    resp = await client.post("/api/v1/persons", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


@pytest.fixture()
async def person(client: AsyncClient, editor: dict[str, str]) -> dict[str, Any]:
    return await _create_person(client, editor)


async def _submit(
    client: AsyncClient,
    headers: dict[str, str],
    person_id: str,
    changes: dict[str, Any],
    **extra: Any,
) -> Any:
    body: dict[str, Any] = {
        "action": "update",
        "resource_type": "person",
        "resource_id": person_id,
        "changes": changes,
    }
    body.update(extra)
    return await client.post(CR, headers=headers, json=body)


async def _patch_person(
    client: AsyncClient, headers: dict[str, str], person_id: str, **changes: Any
) -> dict[str, Any]:
    """An ordinary editor PATCH — the "somebody else edited it" half of staleness."""
    current = await client.get(f"/api/v1/persons/{person_id}", headers=headers)
    resp = await client.patch(
        f"/api/v1/persons/{person_id}",
        headers=headers,
        json={**changes, "expected_version": current.json()["data"]["version"]},
    )
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


# ── Submission ───────────────────────────────────────────────────────────────


class TestSubmit:
    async def test_viewer_can_submit_and_the_baseline_is_captured(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        person: dict[str, Any],
        clan_a: dict[str, Any],
    ) -> None:
        resp = await _submit(
            client,
            viewer,
            person["id"],
            {"birth_date": "1920-05-03"},
            note="Gia phả cũ ghi năm Canh Thân",
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]

        assert data["status"] == "pending"
        assert data["requester_id"] == str(clan_a["viewer_id"])
        assert data["clan_id"] == str(clan_a["clan_id"])
        assert data["changes"] == {"birth_date": "1920-05-03"}
        assert data["note"] == "Gia phả cũ ghi năm Canh Thân"
        # Both halves of the staleness baseline are recorded at submit.
        assert data["target"]["base_version"] == person["version"]
        assert data["target"]["current_version"] == person["version"]
        assert data["target"]["is_stale"] is False
        assert data["target"]["conflicts"] == []

    async def test_stored_payload_snapshots_only_the_proposed_fields(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        person: dict[str, Any],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """A full row copy would be a second, staler mirror of the person record —
        and would drag contact PII into the payload for no benefit."""
        cr_id = (await _submit(client, viewer, person["id"], {"birth_place": "Nam Định"})).json()[
            "data"
        ]["id"]

        async with session_factory() as s:
            payload = await s.scalar(
                sa.text("SELECT payload FROM change_requests WHERE id = :id"),
                {"id": uuid.UUID(cr_id)},
            )

        assert payload["changes"] == {"birth_place": "Nam Định"}
        assert payload["base_values"] == {"birth_place": "Hà Nội"}
        assert payload["base_version"] == person["version"]

    async def test_editor_and_admin_may_also_submit(
        self,
        client: AsyncClient,
        editor: dict[str, str],
        admin: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        for headers in (editor, admin):
            resp = await _submit(client, headers, person["id"], {"notes": "n"})
            assert resp.status_code == 201, resp.text

    async def test_empty_changes_rejected(
        self, client: AsyncClient, viewer: dict[str, str], person: dict[str, Any]
    ) -> None:
        resp = await _submit(client, viewer, person["id"], {})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "change_request.no_changes"

    @pytest.mark.parametrize("bad_field", ["phone", "email", "avatar_url", "nonsense"])
    async def test_non_submittable_field_rejected(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        person: dict[str, Any],
        bad_field: str,
    ) -> None:
        resp = await _submit(client, viewer, person["id"], {bad_field: "x"})
        assert resp.status_code == 422
        body = resp.json()["error"]
        assert body["code"] == "change_request.field_not_submittable"
        assert body["detail"]["fields"] == [bad_field]

    @pytest.mark.parametrize(
        ("action", "resource_type"),
        [("create", "person"), ("delete", "person"), ("update", "marriage")],
    )
    async def test_out_of_scope_operations_rejected(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        person: dict[str, Any],
        action: str,
        resource_type: str,
    ) -> None:
        resp = await _submit(
            client, viewer, person["id"], {"notes": "n"}, action=action, resource_type=resource_type
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "change_request.unsupported_operation"

    async def test_malformed_value_is_422_not_500(
        self, client: AsyncClient, viewer: dict[str, str], person: dict[str, Any]
    ) -> None:
        resp = await _submit(client, viewer, person["id"], {"birth_date": "not-a-date"})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    async def test_unknown_person_is_404(self, client: AsyncClient, viewer: dict[str, str]) -> None:
        resp = await _submit(client, viewer, str(uuid.uuid4()), {"notes": "n"})
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "person_not_found"

    async def test_soft_deleted_person_cannot_be_targeted(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        admin: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        """A deleted person is invisible on the read paths; proposals match that."""
        assert (
            await client.delete(f"/api/v1/persons/{person['id']}", headers=admin)
        ).status_code == 200
        resp = await _submit(client, viewer, person["id"], {"notes": "n"})
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "person_not_found"


# ── Role enforcement ─────────────────────────────────────────────────────────


class TestRoles:
    async def test_viewer_may_not_approve_or_reject(
        self, client: AsyncClient, viewer: dict[str, str], person: dict[str, Any]
    ) -> None:
        cr_id = (await _submit(client, viewer, person["id"], {"notes": "n"})).json()["data"]["id"]
        for action in ("approve", "reject"):
            resp = await client.post(f"{CR}/{cr_id}/{action}", headers=viewer, json={})
            assert resp.status_code == 403, resp.text
            assert resp.json()["error"]["code"] == "insufficient_permissions"
        # ...and nothing was applied.
        after = await client.get(f"{CR}/{cr_id}", headers=viewer)
        assert after.json()["data"]["status"] == "pending"

    async def test_editor_may_approve(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        cr_id = (await _submit(client, viewer, person["id"], {"birth_place": "Huế"})).json()[
            "data"
        ]["id"]
        resp = await client.post(f"{CR}/{cr_id}/approve", headers=editor, json={})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "approved"

    async def test_admin_may_approve(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        admin: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        cr_id = (await _submit(client, viewer, person["id"], {"birth_place": "Huế"})).json()[
            "data"
        ]["id"]
        resp = await client.post(f"{CR}/{cr_id}/approve", headers=admin, json={})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "approved"

    async def test_viewer_sees_only_their_own_proposals(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        mine = (await _submit(client, viewer, person["id"], {"notes": "mine"})).json()["data"]["id"]
        theirs = (await _submit(client, editor, person["id"], {"notes": "theirs"})).json()["data"][
            "id"
        ]

        viewer_ids = {row["id"] for row in (await client.get(CR, headers=viewer)).json()["data"]}
        assert viewer_ids == {mine}
        # Fetching someone else's by id is a 404, not a 403 — the queue is not an
        # enumeration oracle (ADR-021).
        assert (await client.get(f"{CR}/{theirs}", headers=viewer)).status_code == 404

        reviewer_ids = {row["id"] for row in (await client.get(CR, headers=editor)).json()["data"]}
        assert reviewer_ids == {mine, theirs}


# ── Applying an approval ─────────────────────────────────────────────────────


class TestApproval:
    async def test_approval_applies_the_change_through_the_person_write_path(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        cr_id = (
            await _submit(
                client,
                viewer,
                person["id"],
                {"birth_date": "1920-05-03", "birth_date_precision": "exact"},
            )
        ).json()["data"]["id"]

        resp = await client.post(
            f"{CR}/{cr_id}/approve", headers=editor, json={"review_notes": "khớp gia phả"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "approved"
        assert data["review_notes"] == "khớp gia phả"
        assert data["reviewed_at"] is not None

        after = (await client.get(f"/api/v1/persons/{person['id']}", headers=viewer)).json()["data"]
        assert after["birth_date"]["date"] == "1920-05-03"
        # The ordinary write path ran, so OCC advanced exactly as a PATCH would.
        assert after["version"] == person["version"] + 1
        assert data["target"]["current_version"] == after["version"]

    async def test_approval_writes_both_audit_rows_in_one_transaction(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        person: dict[str, Any],
        clan_a: dict[str, Any],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The approval and the edit it caused are both attributable (ADR-014)."""
        cr_id = (await _submit(client, viewer, person["id"], {"birth_place": "Huế"})).json()[
            "data"
        ]["id"]
        assert (
            await client.post(f"{CR}/{cr_id}/approve", headers=editor, json={})
        ).status_code == 200

        async with session_factory() as s:
            rows = (
                (
                    await s.execute(
                        sa.text(
                            "SELECT action, actor_id, resource_id FROM audit_logs "
                            "WHERE clan_id = :cid ORDER BY created_at"
                        ),
                        {"cid": clan_a["clan_id"]},
                    )
                )
                .mappings()
                .all()
            )

        by_action = {row["action"]: row for row in rows}
        assert "change_request.submit" in by_action
        assert "change_request.approve" in by_action
        assert "person.update" in by_action
        # The requester proposed; the reviewer authorized the write, so the person
        # edit is attributed to the reviewer.
        assert by_action["change_request.submit"]["actor_id"] == clan_a["viewer_id"]
        assert by_action["change_request.approve"]["actor_id"] == clan_a["editor_id"]
        assert by_action["person.update"]["actor_id"] == clan_a["editor_id"]
        assert by_action["person.update"]["resource_id"] == uuid.UUID(person["id"])

    async def test_rejection_leaves_the_person_untouched(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        cr_id = (await _submit(client, viewer, person["id"], {"birth_place": "Sai"})).json()[
            "data"
        ]["id"]
        resp = await client.post(
            f"{CR}/{cr_id}/reject", headers=editor, json={"review_notes": "không có nguồn"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "rejected"

        after = (await client.get(f"/api/v1/persons/{person['id']}", headers=viewer)).json()["data"]
        assert after["birth_place"] == "Hà Nội"
        assert after["version"] == person["version"]

    @pytest.mark.parametrize("first", ["approve", "reject"])
    @pytest.mark.parametrize("second", ["approve", "reject"])
    async def test_a_reviewed_request_cannot_be_reviewed_again(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        person: dict[str, Any],
        first: str,
        second: str,
    ) -> None:
        cr_id = (await _submit(client, viewer, person["id"], {"notes": "n"})).json()["data"]["id"]
        assert (
            await client.post(f"{CR}/{cr_id}/{first}", headers=editor, json={})
        ).status_code == 200

        before = (await client.get(f"/api/v1/persons/{person['id']}", headers=viewer)).json()[
            "data"
        ]["version"]
        resp = await client.post(f"{CR}/{cr_id}/{second}", headers=editor, json={})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "change_request.not_pending"
        # Crucially, the rejected second review did NOT re-apply the edit.
        after = (await client.get(f"/api/v1/persons/{person['id']}", headers=viewer)).json()[
            "data"
        ]["version"]
        assert after == before

    async def test_unknown_change_request_is_404(
        self, client: AsyncClient, editor: dict[str, str]
    ) -> None:
        resp = await client.post(f"{CR}/{uuid.uuid4()}/approve", headers=editor, json={})
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "change_request_not_found"


# ── The headline: staleness ──────────────────────────────────────────────────


class TestStaleness:
    """A proposal sits while somebody else edits the same person (ADR-037)."""

    async def test_edit_to_an_untouched_field_does_not_block_approval(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        """The point of merging per field: a birth-date fix survives a bio rewrite."""
        cr_id = (await _submit(client, viewer, person["id"], {"birth_date": "1920-05-03"})).json()[
            "data"
        ]["id"]

        await _patch_person(client, editor, person["id"], biography="Viết lại tiểu sử")

        # The reviewer is TOLD the record moved, before they act...
        pending = (await client.get(f"{CR}/{cr_id}", headers=editor)).json()["data"]
        assert pending["target"]["is_stale"] is True
        assert pending["target"]["current_version"] == person["version"] + 1
        assert pending["target"]["conflicts"] == []

        # ...and approval still lands, keeping BOTH edits.
        resp = await client.post(f"{CR}/{cr_id}/approve", headers=editor, json={})
        assert resp.status_code == 200, resp.text
        after = (await client.get(f"/api/v1/persons/{person['id']}", headers=viewer)).json()["data"]
        assert after["birth_date"]["date"] == "1920-05-03"
        assert after["biography"] == "Viết lại tiểu sử"

    async def test_edit_to_a_proposed_field_blocks_approval_and_loses_nothing(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        """The failure OCC exists to prevent: one correction must not wipe another."""
        cr_id = (await _submit(client, viewer, person["id"], {"birth_date": "1920-05-03"})).json()[
            "data"
        ]["id"]

        await _patch_person(client, editor, person["id"], birth_date="1921-12-31")

        resp = await client.post(f"{CR}/{cr_id}/approve", headers=editor, json={})
        assert resp.status_code == 409, resp.text
        body = resp.json()["error"]
        assert body["code"] == "change_request.target_conflict"
        assert body["detail"]["conflicts"] == [
            {
                "field": "birth_date",
                "base": "1919-01-01",
                "current": "1921-12-31",
                "proposed": "1920-05-03",
            }
        ]

        # The newer edit survives untouched...
        after = (await client.get(f"/api/v1/persons/{person['id']}", headers=viewer)).json()["data"]
        assert after["birth_date"]["date"] == "1921-12-31"
        # ...and the proposal stays actionable rather than being silently consumed.
        detail = (await client.get(f"{CR}/{cr_id}", headers=editor)).json()["data"]
        assert detail["status"] == "pending"
        assert [c["field"] for c in detail["target"]["conflicts"]] == ["birth_date"]

    async def test_someone_else_already_made_the_same_correction(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        """Converging on the proposed value is a no-op, not a lost update."""
        cr_id = (await _submit(client, viewer, person["id"], {"birth_date": "1920-05-03"})).json()[
            "data"
        ]["id"]

        await _patch_person(client, editor, person["id"], birth_date="1920-05-03")

        resp = await client.post(f"{CR}/{cr_id}/approve", headers=editor, json={})
        assert resp.status_code == 200, resp.text
        after = (await client.get(f"/api/v1/persons/{person['id']}", headers=viewer)).json()["data"]
        assert after["birth_date"]["date"] == "1920-05-03"

    async def test_only_the_conflicting_field_blocks_a_multi_field_proposal(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        """Approval is all-or-nothing: a partly-applied proposal is never reported."""
        cr_id = (
            await _submit(
                client,
                viewer,
                person["id"],
                {"birth_date": "1920-05-03", "birth_place": "Nam Định"},
            )
        ).json()["data"]["id"]

        await _patch_person(client, editor, person["id"], birth_place="Huế")

        resp = await client.post(f"{CR}/{cr_id}/approve", headers=editor, json={})
        assert resp.status_code == 409
        assert [c["field"] for c in resp.json()["error"]["detail"]["conflicts"]] == ["birth_place"]
        # Neither field was written — no half-applied proposal.
        after = (await client.get(f"/api/v1/persons/{person['id']}", headers=viewer)).json()["data"]
        assert after["birth_date"]["date"] == "1919-01-01"
        assert after["birth_place"] == "Huế"

    async def test_a_conflicted_proposal_can_still_be_rejected(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        """Rejection has no target preconditions — the queue must stay clearable."""
        cr_id = (await _submit(client, viewer, person["id"], {"birth_date": "1920-05-03"})).json()[
            "data"
        ]["id"]
        await _patch_person(client, editor, person["id"], birth_date="1921-12-31")

        resp = await client.post(f"{CR}/{cr_id}/reject", headers=editor, json={})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "rejected"


class TestSoftDeletedTarget:
    async def test_approval_refused_while_the_target_is_deleted(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        admin: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        cr_id = (await _submit(client, viewer, person["id"], {"birth_place": "Nam Định"})).json()[
            "data"
        ]["id"]
        assert (
            await client.delete(f"/api/v1/persons/{person['id']}", headers=admin)
        ).status_code == 200

        resp = await client.post(f"{CR}/{cr_id}/approve", headers=editor, json={})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "change_request.target_deleted"

        # The reviewer can see why, without guessing.
        detail = (await client.get(f"{CR}/{cr_id}", headers=editor)).json()["data"]
        assert detail["target"]["is_deleted"] is True
        assert detail["status"] == "pending"

    async def test_restoring_the_target_makes_the_proposal_applicable_again(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        admin: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        """delete+restore bumps version twice but touches no proposed field."""
        cr_id = (await _submit(client, viewer, person["id"], {"birth_place": "Nam Định"})).json()[
            "data"
        ]["id"]
        await client.delete(f"/api/v1/persons/{person['id']}", headers=admin)
        assert (
            await client.post(f"/api/v1/persons/{person['id']}/restore", headers=admin)
        ).status_code == 200

        detail = (await client.get(f"{CR}/{cr_id}", headers=editor)).json()["data"]
        assert detail["target"]["is_deleted"] is False
        assert detail["target"]["is_stale"] is True  # version moved...
        assert detail["target"]["conflicts"] == []  # ...but no proposed fact did

        resp = await client.post(f"{CR}/{cr_id}/approve", headers=editor, json={})
        assert resp.status_code == 200, resp.text
        after = (await client.get(f"/api/v1/persons/{person['id']}", headers=viewer)).json()["data"]
        assert after["birth_place"] == "Nam Định"

    async def test_rejection_works_on_a_deleted_target(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        admin: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        cr_id = (await _submit(client, viewer, person["id"], {"notes": "n"})).json()["data"]["id"]
        await client.delete(f"/api/v1/persons/{person['id']}", headers=admin)
        resp = await client.post(f"{CR}/{cr_id}/reject", headers=editor, json={})
        assert resp.status_code == 200, resp.text


# ── Clan isolation, two-sided ────────────────────────────────────────────────


class TestClanIsolation:
    @pytest.fixture()
    async def a_request(
        self, client: AsyncClient, clan_a: dict[str, Any], person: dict[str, Any]
    ) -> str:
        resp = await _submit(
            client, _headers(clan_a, "viewer"), person["id"], {"birth_place": "Nam Định"}
        )
        assert resp.status_code == 201, resp.text
        request_id: str = resp.json()["data"]["id"]
        return request_id

    async def test_clan_b_cannot_list_clan_a_requests(
        self, client: AsyncClient, clan_b: dict[str, Any], a_request: str
    ) -> None:
        for role in ("admin", "editor", "viewer"):
            resp = await client.get(CR, headers=_headers(clan_b, role))
            assert resp.status_code == 200, resp.text
            assert resp.json()["data"] == []

    async def test_clan_b_cannot_fetch_clan_a_request(
        self, client: AsyncClient, clan_b: dict[str, Any], a_request: str
    ) -> None:
        resp = await client.get(f"{CR}/{a_request}", headers=_headers(clan_b, "admin"))
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "change_request_not_found"

    @pytest.mark.parametrize("action", ["approve", "reject"])
    async def test_clan_b_cannot_review_clan_a_request(
        self,
        client: AsyncClient,
        clan_a: dict[str, Any],
        clan_b: dict[str, Any],
        a_request: str,
        person: dict[str, Any],
        action: str,
    ) -> None:
        resp = await client.post(
            f"{CR}/{a_request}/{action}", headers=_headers(clan_b, "admin"), json={}
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "change_request_not_found"

        # Positive control: the SAME call from clan A succeeds, so the 404 above is
        # isolation and not a broken route.
        ok = await client.post(
            f"{CR}/{a_request}/{action}", headers=_headers(clan_a, "admin"), json={}
        )
        assert ok.status_code == 200, ok.text

    async def test_clan_b_cannot_target_a_clan_a_person(
        self, client: AsyncClient, clan_b: dict[str, Any], person: dict[str, Any]
    ) -> None:
        resp = await _submit(client, _headers(clan_b, "viewer"), person["id"], {"notes": "n"})
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "person_not_found"

    async def test_clan_a_still_sees_its_own(
        self, client: AsyncClient, clan_a: dict[str, Any], a_request: str
    ) -> None:
        resp = await client.get(CR, headers=_headers(clan_a, "admin"))
        assert [row["id"] for row in resp.json()["data"]] == [a_request]


# ── List contract ────────────────────────────────────────────────────────────


class TestListContract:
    async def test_status_filter_and_cursor_envelope(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        person: dict[str, Any],
    ) -> None:
        ids = [
            (await _submit(client, viewer, person["id"], {"notes": f"n{i}"})).json()["data"]["id"]
            for i in range(3)
        ]
        await client.post(f"{CR}/{ids[0]}/reject", headers=editor, json={})

        page1 = await client.get(CR, headers=editor, params={"status": "pending", "limit": 1})
        body = page1.json()
        assert body["meta"]["has_more"] is True
        assert body["meta"]["limit"] == 1
        assert body["meta"]["cursor"]
        assert [row["id"] for row in body["data"]] == [ids[1]]

        page2 = await client.get(
            CR,
            headers=editor,
            params={"status": "pending", "limit": 1, "cursor": body["meta"]["cursor"]},
        )
        assert [row["id"] for row in page2.json()["data"]] == [ids[2]]
        assert page2.json()["meta"]["has_more"] is False
        assert page2.json()["meta"]["cursor"] is None

    async def test_tampered_cursor_is_400_invalid_cursor(
        self, client: AsyncClient, editor: dict[str, str]
    ) -> None:
        resp = await client.get(CR, headers=editor, params={"cursor": "not-a-cursor"})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "invalid_cursor"

    async def test_no_contact_pii_reaches_the_review_surface(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
    ) -> None:
        """The target block echoes proposed fields only, and PII is not proposable."""
        subject = await _create_person(
            client, editor, phone="0900000000", email="cu.to@example.com"
        )
        cr_id = (await _submit(client, viewer, subject["id"], {"birth_place": "Nam Định"})).json()[
            "data"
        ]["id"]
        detail = (await client.get(f"{CR}/{cr_id}", headers=editor)).text
        assert "0900000000" not in detail
        assert "cu.to@example.com" not in detail


# ── Under the real RLS request session ───────────────────────────────────────


class TestUnderRlsSession:
    """The flow on a NON-BYPASS request session, as production runs it (ADR-008).

    Every other test here overrides ``get_db`` with a plain sessionmaker, so it runs
    as the privileged migration role and never exercises the RLS seam. That would
    hide two real risks specific to this feature:

    - ``change_requests`` is not in the RLS rollout and has no policy, but the
      request role still needs table grants on it (inherited from migration 002's
      ``GRANT … ON ALL TABLES IN SCHEMA public``, which ran after 001 created the
      table). Without them every endpoint here would 500 in production.
    - Approval's write to ``persons`` must satisfy migration 029's Phase-4
      ``persons_upd USING (membership)`` policy.

    The target person is seeded through a privileged session rather than
    ``POST /api/v1/persons`` **deliberately**: person *creation* is currently broken
    under a real RLS session for reasons unrelated to change requests (the ORM's
    ``INSERT … RETURNING`` is evaluated against ``persons_sel``, whose membership
    predicate cannot hold yet because ``clan_memberships`` is inserted after
    ``persons``). Seeding around it keeps this test honest about what it covers.
    """

    @pytest.fixture(autouse=True)
    def _reset_clan_context(self) -> Generator[None]:
        set_request_clan_id(None)
        yield
        set_request_clan_id(None)

    @pytest.fixture()
    async def rls_client(self, migrated_db_url: str) -> AsyncGenerator[AsyncClient]:
        engine = create_async_engine(migrated_db_url)
        factory = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)
        app = create_app()

        async def _override_db() -> AsyncGenerator[AsyncSession]:
            async with factory() as session:
                yield session

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_current_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac
        await engine.dispose()

    @staticmethod
    async def _seed_person(
        session_factory: async_sessionmaker[AsyncSession], seed: dict[str, Any]
    ) -> uuid.UUID:
        person_id = uuid.uuid4()
        async with session_factory() as s:
            await s.execute(
                sa.text(
                    "INSERT INTO persons "
                    "(id, full_name, birth_place, created_by_clan_id, created_by) "
                    "VALUES (:i, 'Cụ Tổ', 'Hà Nội', :c, :a)"
                ),
                {"i": person_id, "c": seed["clan_id"], "a": seed["editor_id"]},
            )
            await s.execute(
                sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
                {"p": person_id, "c": seed["clan_id"]},
            )
            await s.commit()
        return person_id

    async def test_submit_list_and_approve_survive_the_non_bypass_role(
        self,
        rls_client: AsyncClient,
        clan_a: dict[str, Any],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        person_id = await self._seed_person(session_factory, clan_a)
        editor, viewer = _headers(clan_a, "editor"), _headers(clan_a, "viewer")

        submitted = await _submit(rls_client, viewer, str(person_id), {"birth_place": "Nam Định"})
        assert submitted.status_code == 201, submitted.text
        cr_id = submitted.json()["data"]["id"]

        listed = await rls_client.get(CR, headers=editor)
        assert [row["id"] for row in listed.json()["data"]] == [cr_id]

        resp = await rls_client.post(f"{CR}/{cr_id}/approve", headers=editor, json={})
        assert resp.status_code == 200, resp.text
        after = (await rls_client.get(f"/api/v1/persons/{person_id}", headers=viewer)).json()[
            "data"
        ]
        assert after["birth_place"] == "Nam Định"

    async def test_clan_b_still_cannot_reach_clan_a_request(
        self,
        rls_client: AsyncClient,
        clan_a: dict[str, Any],
        clan_b: dict[str, Any],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        person_id = await self._seed_person(session_factory, clan_a)
        cr_id = (
            await _submit(rls_client, _headers(clan_a, "viewer"), str(person_id), {"notes": "n"})
        ).json()["data"]["id"]

        resp = await rls_client.post(
            f"{CR}/{cr_id}/approve", headers=_headers(clan_b, "admin"), json={}
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "change_request_not_found"

        ok = await rls_client.post(
            f"{CR}/{cr_id}/approve", headers=_headers(clan_a, "admin"), json={}
        )
        assert ok.status_code == 200, ok.text


# ── Negative control ─────────────────────────────────────────────────────────


class TestNegativeControl:
    async def test_conflict_guard_is_what_makes_the_stale_case_pass(
        self,
        client: AsyncClient,
        viewer: dict[str, str],
        editor: dict[str, str],
        person: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Remove the merge guard and the headline test's outcome must change.

        Patches ``detect_conflicts`` to always report "no conflict" — the naive
        last-write-wins behaviour this feature exists to avoid — and asserts that the
        approval then silently destroys the newer edit. If this test ever passes
        while ``test_edit_to_a_proposed_field_blocks_approval_and_loses_nothing``
        also passes, the guard is real; if the guard were deleted, the two would
        contradict each other and the suite would fail.
        """
        import app.domain.change_request.entity as entity_module

        cr_id = (await _submit(client, viewer, person["id"], {"birth_date": "1920-05-03"})).json()[
            "data"
        ]["id"]
        await _patch_person(client, editor, person["id"], birth_date="1921-12-31")

        monkeypatch.setattr(entity_module, "detect_conflicts", lambda *args, **kwargs: [])

        resp = await client.post(f"{CR}/{cr_id}/approve", headers=editor, json={})
        assert resp.status_code == 200, resp.text
        after = (await client.get(f"/api/v1/persons/{person['id']}", headers=viewer)).json()["data"]
        # Without the guard the week-old proposal silently reverts the newer edit —
        # exactly the data loss the guard prevents.
        assert after["birth_date"]["date"] == "1920-05-03"
