# PR-J Read-Model Bugs — Design Spec

**Date:** 2026-07-11
**Branch:** `fix/pr-j-readmodel-bugs` (off `main` @ 7fd6d08)
**Scope:** the two remaining PR-J correctness bugs (S3 from the 2026-07-04 seam review). The other
original PR-J items are already resolved: `/tree/ancestors` duplicate-ancestors fixed in PR #63,
and S3-4 audit `clan_id` typing already fixed on `main`.

## Bug A — platform_admin clan detail reports `total_users = 0` until a clan has its first person

`app/infrastructure/persistence/platform_admin_query_port.py::get_clan_detail` (lines 63-71) computes
both stats from a single query anchored on `ClanMembership`, outer-joined to `UserClanRole` on
`clan_id`:

```python
select(
    func.count(func.distinct(ClanMembership.id)).label("total_members"),
    func.count(func.distinct(UserClanRole.id)).label("total_users"),
).select_from(ClanMembership)
 .outerjoin(UserClanRole, UserClanRole.clan_id == ClanMembership.clan_id)
 .where(ClanMembership.clan_id == clan_id)
```

**Defect:** the FROM/WHERE is anchored on `ClanMembership`. A clan with **zero** person-memberships
produces **no rows**, so `count(...)` returns 0 for *both* labels — `total_users` reads 0 even when
users hold roles in that clan (e.g. a freshly created clan whose founder registered but hasn't added
any `person` rows yet). Members (persons linked to the clan) and users (accounts with a role in the
clan) are independent entities; coupling them through one join makes each wrong when the other is empty.

**Fix:** compute the two counts **independently**, clan-scoped, mirroring the `get_metrics` method
just below (which already uses independent scalar subqueries):

- `total_members` = distinct **non-soft-deleted** persons in the clan
  → `count(distinct Person.id)` over `ClanMembership` joined to `Person`, `Person.is_deleted = false`,
  `ClanMembership.clan_id = clan_id`. (Consistent with `get_metrics`, which counts
  `Person where is_deleted = false`. This changes the current behavior, which counted every membership
  regardless of person soft-delete — owner-approved.)
- `total_users` = distinct users with a role in the clan
  → `count(distinct UserClanRole.user_id)` where `UserClanRole.clan_id = clan_id`.
  Counts all role rows regardless of `is_approved`, matching the platform-wide `get_metrics` semantics.

No schema/migration change. `ClanDetailView` / `ClanStatsView` shapes are unchanged.

## Bug B — person includes silently swallowed to `[]` on error

`app/api/v1/persons.py::_fetch_included_data` (lines 215-219):

```python
results = await asyncio.gather(*tasks.values(), return_exceptions=True)
res_dict = {}
for key, res in zip(tasks.keys(), results, strict=False):
    res_dict[key] = res if isinstance(res, list) else []
return res_dict
```

**Defect:** `return_exceptions=True` turns a raised exception from any include sub-query
(`marriages` / `parent_child` / `timeline` / `documents`) into a value; the `isinstance(res, list)`
guard then coerces it to `[]`. The client receives an empty list instead of an error — a silent
data-integrity failure that hides real backend faults (DB error, clan-scope bug, etc.).

**Fix:** after gathering, **re-raise the first exception** so it propagates to the app's registered
exception handlers (structured envelope / correct status), instead of masking it as empty data.
Concurrent gathering is preserved (still one `gather`); only the error handling changes:

```python
results = await asyncio.gather(*tasks.values(), return_exceptions=True)
res_dict: dict[str, list[Any]] = {}
for key, res in zip(tasks.keys(), results, strict=False):
    if isinstance(res, BaseException):
        raise res
    res_dict[key] = res
return res_dict
```

(Re-raising `BaseException` preserves the original error type — including the domain errors the
handler methods raise — so the existing exception handlers produce the same envelope they would for
a non-batched request.)

## Testing (real-DB integration; per project verification discipline)

**Bug A:**
- Seed a clan with **users holding roles but zero person-memberships** → `total_users` equals the
  number of distinct role-holders (not 0); `total_members == 0`.
- Seed a clan with N persons (one soft-deleted) and M distinct users with roles →
  `total_members == N-1` (soft-deleted excluded), `total_users == M`.
- Two clans: counts for clan A never include clan B's members/users (clan isolation).

**Bug B:**
- Monkeypatch one include handler method (e.g. `get_timeline`) to raise → the persons read endpoint
  (or `_fetch_included_data`) **propagates** the error (raises / non-200), and does **not** return
  `{"timeline": []}`.
- Happy path unchanged: all includes return their real lists.

Quality gate (full): `uv run pytest`, `uvx ruff check .`, `uvx ruff format --check .`,
`uv run mypy app/ tests/`, `lint-imports`.

## Out of scope (explicit YAGNI, owner-confirmed)

- S3 minors: divorce events never surfaced on the timeline; person search not returning `birth_name`.
  These are behavior/feature changes, not correctness bugs — deferred; noted for a later pass.
- Typed read-model DTOs for the remaining `dict[str, Any]` query ports — separate YAGNI-scrutinized
  effort, not pulled in here.
