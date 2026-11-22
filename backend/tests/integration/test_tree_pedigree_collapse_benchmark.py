"""#398: how far does ``get_family_tree_flat`` fan out under pedigree collapse?

``get_family_tree_flat`` (migration 013) is a recursive CTE whose only cycle guard is
per path (``NOT (p.id = ANY(d.path))``). A person reachable through two in-tree parents
(two cousins who marry) comes back once per lineage path, and so does every descendant
below them. ``build_descendants_tree`` keeps the first row per person, but checks its
50,000 cap (``_MAX_TREE_NODES``) against the ROW count. This module measures the
fan-out, so a fix can be chosen from numbers. It changes nothing in the app.

Two tests:

* ``test_cousin_marriage_fans_out_rows`` is the negative control. It runs in the
  default suite: one cousin marriage with one child gives ``rows > distinct_persons``,
  and the same assertion fails on the same family without the marriage.
* ``test_benchmark_pedigree_collapse_fan_out`` is the benchmark. It is marked ``slow``
  and is SKIPPED unless ``FAMILYROOTS_BENCH_TREE=1``, because ``pyproject.toml``
  declares ``slow`` but no ``addopts`` deselects it. It seeds one clan of about 5,000
  persons across 12 generations at three collapse levels (0, 5 and 20 cousin
  marriages, each couple with children) and prints, per level: the rows the CTE
  returns, the distinct persons among them, the CTE time, the time of the
  ``compute_generation_map`` edge read, and the end-to-end ``GET /tree`` time at the
  default depth. Run it with::

      FAMILYROOTS_BENCH_TREE=1 uv run pytest -s -m slow \\
          tests/integration/test_tree_pedigree_collapse_benchmark.py

The results are recorded in ``docs/architecture/tree-read-model.md`` § "Performance
guards". ``GET /tree`` is driven through the RS256/JWKS harness of
``test_founder_designation.py``, with ``get_db`` on the plain privileged maker, so the
HTTP time does not include the RLS seam.
"""

from __future__ import annotations

import json
import os
import statistics
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.security as security_module
from app.core.database import get_db
from app.main import create_app
from app.services.tree_builder import _MAX_TREE_NODES, compute_generation_map

pytestmark = pytest.mark.integration

BENCH_ENV = "FAMILYROOTS_BENCH_TREE"
_KID = "tree-bench-key"
_DEFAULT_DEPTH = 10  # GET /tree's max_generations default (app/api/v1/tree.py)
_FULL_DEPTH = 50  # the endpoint's maximum, deep enough for the whole clan
_RUNS = 5

# Persons per generation for the blood line. 12 generations, 3,323 descendants; every
# descendant with children gets one married-in spouse (1,923), so about 5,246 persons.
_GENERATION_SIZES = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 900, 1400)
# Generations (0-based index into _GENERATION_SIZES) the cousin marriages cycle through.
_MARRIAGE_GENERATIONS = (4, 5, 6, 7, 8, 9, 10)


# ── the family graph, built in memory, then bulk-inserted ────────────────────


@dataclass
class _Family:
    clan_id: uuid.UUID = field(default_factory=uuid.uuid4)
    persons: list[dict[str, Any]] = field(default_factory=list)
    edges: list[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=list)  # (parent, child)
    marriages: list[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=list)
    founder: uuid.UUID | None = None

    def person(self, gender: str, name: str, *, blood: bool) -> uuid.UUID:
        pid = uuid.uuid4()
        self.persons.append({"id": pid, "gender": gender, "name": name, "blood": blood})
        return pid


def _build_family(cousin_marriages: int) -> tuple[_Family, int]:
    """The blood line of _GENERATION_SIZES, children assigned to parents in contiguous
    blocks (siblings are neighbours, so cousins are near each other). Every parent has
    a married-in spouse who is the other parent of all their children.

    A cousin marriage pairs a man X and a woman Y of the same generation with different
    parents and the same grandparent. X's children take Y as their mother instead of
    X's married-in wife, who stays in the clan with no edge, so every collapse level has
    the same number of persons. Y keeps her own children with her husband. X's children
    are then reachable from the founder through X and through Y.

    Returns the family and the number of cousin marriages actually placed.
    """
    fam = _Family()
    gens: list[list[uuid.UUID]] = []
    gender: dict[uuid.UUID, str] = {}
    parent_of: dict[uuid.UUID, uuid.UUID] = {}
    for g, size in enumerate(_GENERATION_SIZES):
        row: list[uuid.UUID] = []
        for j in range(size):
            sex = "male" if j % 2 == 0 else "female"
            pid = fam.person(sex, f"G{g + 1}-{j}", blood=True)
            gender[pid] = sex
            if g > 0:
                parent_of[pid] = gens[g - 1][j * len(gens[g - 1]) // size]
            row.append(pid)
        gens.append(row)
    fam.founder = gens[0][0]

    # Pick the cousin couples before wiring edges.
    used: set[uuid.UUID] = set()
    couples: dict[uuid.UUID, uuid.UUID] = {}  # husband -> cousin wife
    for k in range(cousin_marriages):
        g = _MARRIAGE_GENERATIONS[k % len(_MARRIAGE_GENERATIONS)]
        row = gens[g]
        start = (k * 7919) % len(row)
        found = False
        for step in range(len(row)):
            x = row[(start + step) % len(row)]
            if gender[x] != "male" or x in used:
                continue
            for y in row:
                if (
                    gender[y] == "female"
                    and y not in used
                    and parent_of[y] != parent_of[x]
                    and parent_of[parent_of[y]] == parent_of[parent_of[x]]
                ):
                    couples[x] = y
                    used.update((x, y))
                    found = True
                    break
            if found:
                break

    children_of: dict[uuid.UUID, list[uuid.UUID]] = {}
    for child, parent in parent_of.items():
        children_of.setdefault(parent, []).append(child)
    for parent, kids in children_of.items():
        other_sex = "female" if gender[parent] == "male" else "male"
        spouse = fam.person(other_sex, f"spouse-of-{parent.hex[:6]}", blood=False)
        mother_or_father = couples.get(parent)
        if mother_or_father is None:
            fam.marriages.append((parent, spouse))
            other = spouse
        else:
            fam.marriages.append((parent, mother_or_father))  # married-in spouse: no edge
            other = mother_or_father
        for kid in kids:
            fam.edges.append((parent, kid))
            fam.edges.append((other, kid))
    return fam, len(couples)


def _insert_family(conn: sa.Connection, fam: _Family) -> None:
    creator = uuid.uuid4()
    conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:c, 'Bench', :s)"),
        {"c": fam.clan_id, "s": f"bench-{fam.clan_id.hex[:8]}"},
    )
    conn.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, :n, :g, :c, :cb)"
        ),
        [
            {"id": p["id"], "n": p["name"], "g": p["gender"], "c": fam.clan_id, "cb": creator}
            for p in fam.persons
        ],
    )
    conn.execute(
        sa.text(
            "INSERT INTO clan_memberships (id, person_id, clan_id, role, is_founder) "
            "VALUES (:id, :p, :c, :r, :f)"
        ),
        [
            {
                "id": uuid.uuid4(),
                "p": p["id"],
                "c": fam.clan_id,
                "r": "blood" if p["blood"] else "spouse",
                "f": p["id"] == fam.founder,
            }
            for p in fam.persons
        ],
    )
    conn.execute(
        sa.text(
            "INSERT INTO parent_child "
            "(id, parent_id, child_id, created_by_clan_id, relationship_type, created_by) "
            "VALUES (:id, :p, :ch, :c, 'biological', :cb)"
        ),
        [
            {"id": uuid.uuid4(), "p": p, "ch": ch, "c": fam.clan_id, "cb": creator}
            for p, ch in fam.edges
        ],
    )
    if not fam.marriages:
        return
    conn.execute(
        sa.text(
            "INSERT INTO marriages (id, person1_id, person2_id, status, spouse_order, "
            " created_by_clan_id, created_by) "
            "VALUES (:id, :a, :b, 'married', 1, :c, :cb)"
        ),
        [
            {"id": uuid.uuid4(), "a": a, "b": b, "c": fam.clan_id, "cb": creator}
            for a, b in fam.marriages
        ],
    )


def _sync_engine(dsn: str) -> sa.Engine:
    return sa.create_engine(dsn.replace("+asyncpg", ""))


def _flat_counts(
    conn: sa.Connection, root: uuid.UUID, clan_id: uuid.UUID, depth: int
) -> tuple[int, int]:
    """(rows, distinct persons) that get_family_tree_flat returns."""
    row = conn.execute(
        sa.text(
            "SELECT count(*) AS n_rows, count(DISTINCT person_id) AS n_persons "
            "FROM public.get_family_tree_flat(:r, :c, :d)"
        ),
        {"r": root, "c": clan_id, "d": depth},
    ).one()
    return int(row.n_rows), int(row.n_persons)


def _assert_fan_out(rows: int, distinct_persons: int) -> None:
    assert rows > distinct_persons, f"no fan-out: {rows} rows, {distinct_persons} persons"


# ── negative control (default suite) ─────────────────────────────────────────


def _seed_cousins(conn: sa.Connection, *, marry: bool) -> tuple[uuid.UUID, uuid.UUID]:
    """Founder F; sons S1, S2; S1's son C1 and S2's daughter C2 are first cousins.
    With ``marry``, C1 and C2 marry and have one child K (edges from both)."""
    fam = _Family()
    f = fam.person("male", "F", blood=True)
    fam.founder = f
    s1 = fam.person("male", "S1", blood=True)
    s2 = fam.person("male", "S2", blood=True)
    c1 = fam.person("male", "C1", blood=True)
    c2 = fam.person("female", "C2", blood=True)
    fam.edges += [(f, s1), (f, s2), (s1, c1), (s2, c2)]
    if marry:
        k = fam.person("male", "K", blood=True)
        fam.marriages.append((c1, c2))
        fam.edges += [(c1, k), (c2, k)]
    _insert_family(conn, fam)
    return fam.clan_id, f


def test_cousin_marriage_fans_out_rows(migrated_db_url: str) -> None:
    eng = _sync_engine(migrated_db_url)
    try:
        with eng.begin() as conn:
            married_clan, married_root = _seed_cousins(conn, marry=True)
            plain_clan, plain_root = _seed_cousins(conn, marry=False)
        with eng.connect() as conn:
            rows, persons = _flat_counts(conn, married_root, married_clan, _DEFAULT_DEPTH)
            _assert_fan_out(rows, persons)
            assert (rows, persons) == (7, 6)  # K once through C1 and once through C2

            # The control: the same family without the marriage. The same assertion fails.
            rows, persons = _flat_counts(conn, plain_root, plain_clan, _DEFAULT_DEPTH)
            assert rows == persons == 5
            with pytest.raises(AssertionError, match="no fan-out"):
                _assert_fan_out(rows, persons)
    finally:
        eng.dispose()


# ── the benchmark (opt-in) ───────────────────────────────────────────────────


def _public_jwk(pem: str) -> dict[str, Any]:
    key = serialization.load_pem_public_key(pem.encode())
    jwk: dict[str, Any] = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key))  # type: ignore[arg-type]
    return jwk


@pytest.fixture()
def rsa_keys() -> Iterator[dict[str, Any]]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    public_jwk = _public_jwk(public_pem)
    public_jwk.update({"kid": _KID, "use": "sig", "alg": "RS256"})
    old_cache, old_time = security_module._jwks_cache, security_module._jwks_cache_time
    security_module._jwks_cache = {"keys": [public_jwk]}
    security_module._jwks_cache_time = time.monotonic()
    yield {"private_pem": private_pem}
    security_module._jwks_cache, security_module._jwks_cache_time = old_cache, old_time


def _mint(private_pem: str, user_id: uuid.UUID, email: str) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "iss": f"{security_module.settings.SUPABASE_URL.rstrip('/')}/auth/v1",  # type: ignore[attr-defined]
        "iat": now,
        "exp": now + timedelta(hours=1),
        "user_metadata": {"full_name": "Bench"},
    }
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": _KID})


def _seed_viewer(conn: sa.Connection, clan_id: uuid.UUID) -> tuple[uuid.UUID, str]:
    user_id = uuid.uuid4()
    email = f"bench-{user_id.hex[:8]}@ex.com"
    conn.execute(
        sa.text(
            "INSERT INTO user_profiles (id, email, display_name, is_active) "
            "VALUES (:u, :e, 'U', true)"
        ),
        {"u": user_id, "e": email},
    )
    conn.execute(
        sa.text(
            "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved, "
            "approved_by, approved_at) VALUES (:u, :c, 'viewer', true, :u, now())"
        ),
        {"u": user_id, "c": clan_id},
    )
    return user_id, email


def _median_ms(samples: list[float]) -> float:
    return round(statistics.median(samples) * 1000, 1)


def _time_flat_sql(conn: sa.Connection, root: uuid.UUID, clan_id: uuid.UUID, depth: int) -> float:
    """Median wall time of the exact statement build_descendants_tree issues, all rows
    fetched to the client."""
    samples = []
    for _ in range(_RUNS):
        t0 = time.perf_counter()
        conn.execute(
            sa.text("SELECT * FROM public.get_family_tree_flat(:r, :c, :d)"),
            {"r": root, "c": clan_id, "d": depth},
        ).all()
        samples.append(time.perf_counter() - t0)
    return _median_ms(samples)


async def _time_generation_map(
    dsn: str, clan_id: uuid.UUID, founder: uuid.UUID
) -> tuple[float, float, int]:
    """(edge-read statement ms, whole compute_generation_map ms, đời entries). With
    ``founder_id`` passed, the edge read is the only statement the function issues."""
    engine = create_async_engine(dsn)
    stmt_samples: list[float] = []
    call_samples: list[float] = []
    started: list[float] = []
    entries = 0

    def _before(*_args: Any) -> None:
        started.append(time.perf_counter())

    def _after(*_args: Any) -> None:
        stmt_samples.append(time.perf_counter() - started.pop())

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with maker() as session:
            await session.execute(sa.text("SELECT 1"))  # open the connection first
            sa.event.listen(engine.sync_engine, "before_cursor_execute", _before)
            sa.event.listen(engine.sync_engine, "after_cursor_execute", _after)
            try:
                for _ in range(_RUNS):
                    t0 = time.perf_counter()
                    doi = await compute_generation_map(session, clan_id, founder_id=founder)
                    call_samples.append(time.perf_counter() - t0)
                    entries = len(doi)
            finally:
                sa.event.remove(engine.sync_engine, "before_cursor_execute", _before)
                sa.event.remove(engine.sync_engine, "after_cursor_execute", _after)
    finally:
        await engine.dispose()
    assert len(stmt_samples) == _RUNS  # one statement per call: the edge read
    return _median_ms(stmt_samples), _median_ms(call_samples), entries


@pytest.mark.slow
@pytest.mark.skipif(not os.environ.get(BENCH_ENV), reason=f"benchmark: set {BENCH_ENV}=1")
async def test_benchmark_pedigree_collapse_fan_out(
    migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    app = create_app()
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_db() -> Any:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    eng = _sync_engine(migrated_db_url)
    results: list[dict[str, Any]] = []
    try:
        for level in (0, 5, 20):
            fam, placed = _build_family(level)
            assert placed == level, f"only {placed} of {level} cousin marriages placed"
            assert fam.founder is not None
            with eng.begin() as conn:
                _insert_family(conn, fam)
                user_id, email = _seed_viewer(conn, fam.clan_id)
            with eng.connect() as conn:
                conn.execute(sa.text("ANALYZE persons, clan_memberships, parent_child, marriages"))
                conn.commit()
                rows, persons = _flat_counts(conn, fam.founder, fam.clan_id, _DEFAULT_DEPTH)
                rows_full, persons_full = _flat_counts(conn, fam.founder, fam.clan_id, _FULL_DEPTH)
                sql_ms = _time_flat_sql(conn, fam.founder, fam.clan_id, _DEFAULT_DEPTH)
                sql_full_ms = _time_flat_sql(conn, fam.founder, fam.clan_id, _FULL_DEPTH)
            edge_ms, map_ms, doi_entries = await _time_generation_map(
                migrated_db_url, fam.clan_id, fam.founder
            )

            token = _mint(rsa_keys["private_pem"], user_id, email)
            headers = {"Authorization": f"Bearer {token}", "X-Current-Clan-Id": str(fam.clan_id)}
            http_samples: list[float] = []
            total_persons = None
            # No ``with``: the lifespan (Sentry, Firebase, the RLS readiness probe on the
            # configured app database) is not part of a request, as in the founder harness.
            client = TestClient(app)
            for _ in range(_RUNS):
                t0 = time.perf_counter()
                resp = client.get("/api/v1/tree", headers=headers)
                http_samples.append(time.perf_counter() - t0)
                assert resp.status_code == 200, resp.text
                total_persons = resp.json()["data"]["total_persons"]

            result = {
                "cousin_marriages": level,
                "clan_persons": len(fam.persons),
                "edges": len(fam.edges),
                "doi_entries": doi_entries,
                "rows_d10": rows,
                "persons_d10": persons,
                "fan_out_d10": rows - persons,
                "rows_d50": rows_full,
                "persons_d50": persons_full,
                "fan_out_d50": rows_full - persons_full,
                "flat_sql_ms_d10": sql_ms,
                "flat_sql_ms_d50": sql_full_ms,
                "edge_read_ms": edge_ms,
                "generation_map_ms": map_ms,
                "get_tree_ms": _median_ms(http_samples),
                "get_tree_total_persons": total_persons,
            }
            results.append(result)
            print(f"\n[#398] {json.dumps(result)}")

            # The builder dedupes, so the response counts persons, not rows.
            assert total_persons == persons
            if level == 0:
                assert rows == persons and rows_full == persons_full
            else:
                print(f"[#398] level {level}: rows - distinct_persons = {rows - persons} (d10)")
                assert rows - persons > 0
                assert rows_full - persons_full > 0
    finally:
        eng.dispose()
        await engine.dispose()

    worst = max(r["rows_d50"] / r["persons_d50"] for r in results)
    print(
        f"\n[#398] cap {_MAX_TREE_NODES} rows; worst rows/person ratio {worst:.3f} "
        f"-> cap reached at ~{int(_MAX_TREE_NODES / worst)} distinct persons"
    )
