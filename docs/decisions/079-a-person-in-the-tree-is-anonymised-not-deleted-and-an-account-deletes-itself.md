# ADR-079: A Person in the Tree Is Anonymised, Not Deleted, and an Account Deletes Itself

## Status

Accepted (2026-11-28), resolving issue #333, the technical part of #322. **This ADR ships backend
and web code.** The legal part, who the data controller is and the final notice text, stays open on
#322. The web privacy notice carries a visible "bản nháp — cần rà soát pháp lý" banner until #322
closes.

There is no migration. Two routes are added, and no existing request or response shape changes.

## Context

ADR-073 recorded on 2026-10-18 that once the deployment holds real personal data of people other
than the maintainer, Law 91/2025/QH15 obligations follow. Two rights had no technical path:

- **Someone with an account could not leave.** Nothing removed a Supabase account, its clan roles,
  or its `user_profiles` row. `IdentityProvider.delete_user` existed only to compensate a failed
  registration.
- **Someone in a tree could not be removed from it without breaking it.** `DELETE /persons/{id}`
  soft-deletes the node. Its edges stay (ADR-051), but the tree builder drops a soft-deleted
  person, and every descendant reached through that person drops with it. Their đời can no longer
  be computed from thủy tổ (ADR-027). A hard delete would do the same, permanently.

## Decision

### 1. Anonymise, not delete

`POST /api/v1/persons/{id}/anonymise` (admin only, clan-scoped like every person write) works as
follows:

- **The name.** `full_name` becomes **"Đã ẩn danh"**.
- **Cleared to null.** The other names (birth name, tên tự / `courtesy_name`, tên húy and tên thụy /
  `posthumous_name`, alias). Both solar dates and their display text, with precision set to
  `unknown`. Both lunar dates. The five places. Biography and notes. Religion, occupation,
  education, title. Phone and email. `avatar_url`. The public avatar object is taken down
  best-effort, as `DELETE` does.
- **Kept.**
  - The row, live (`is_deleted` stays false).
  - `gender`, because con theo đời cha reads it to choose the canonical parent.
  - `nationality`, which is not identifying and is non-null in the domain.
  - The clan membership, the founder flag, the branch, and every `parent_child` and `marriages` row.

So the tree keeps its shape, and đời is unchanged for the person and for every descendant.

**The audit row does not copy what it removes.** `PersonAnonymised`, action `person.anonymise`,
carries `new_value = {"full_name": "Đã ẩn danh", "cleared_fields": [...]}` and `old_value = null`.
Reusing `Person.update` would have written every old name and date into `audit_logs.old_value`.

### 2. An account deletes itself

`DELETE /api/v1/me`, in this order:

1. **Last-admin check.** Lock the approved-admin rows of every clan the caller administers
   (`FOR UPDATE`, ordered by id, the same rows and order as `lock_admin_count`). If the caller is
   any clan's **only** approved admin, answer **403 `account.last_admin_transfer_first`** with
   `detail.clan_ids`, and change nothing.
2. **Delete the caller's rows.** Every `user_clan_roles` row (approved or pending, in every clan),
   every `identity_claims` row, and every `user_fcm_tokens` row.
3. **Tombstone the profile row.**
   - `email` becomes `deleted-<id>@deleted.invalid`, a reserved domain; the column is NOT NULL and
     unique, so each tombstone gets its own address.
   - `display_name`, `avatar_url`, `person_id` and `last_login_at` become null, and `platform_role`
     becomes `user`.
   - `is_active` becomes false.
4. **Audit.** Write `account.delete` rows: one per clan left, with that `clan_id`, so each clan's
   trail shows the departure, and one platform row with `clan_id = null`. None of them carries the
   email.
5. **Commit, then call the provider.** Commit, and only then call `IdentityProvider.delete_user`,
   holding no transaction (ADR-028).

**Why a tombstone and not a deleted row.** The provider's access token stays valid until it expires
(up to an hour). With the row gone, `ensure_user_profile` would re-create a profile from that
token's email and name on the next request, putting personal data back. With the row tombstoned,
`get_current_user` answers `account_deactivated`.

**Why the database step goes first.** If the provider call fails after the commit, the account is
already scrubbed and deactivated, and the provider error surfaces as 503. The route verifies the
token **without** the deactivation gate (`get_verified_token`, used by this route only), so the
same request again finishes the job. The Supabase adapter treats a 404 from `delete_user` as
already deleted. The reverse order would leave personal data behind with no way to retry.

**Why the system session.** The route has no clan context and spans every clan the caller belongs
to. `user_clan_roles` DELETE is clan-keyed for the request role (ADR-050), so a request session
would delete nothing, silently. `identity_claims` is deny-all for the request role (ADR-042). Every
statement is keyed on the verified token's own `sub`, never on input. This is the same reasoning as
the claim handlers and invitation accept (ADR-048).

**The tree is clan data, not account data.** The person an account was linked to stays in the tree,
unlinked. If that person should leave the tree too, a clan admin anonymises them (§ 1).

## Consequences

- **Readings** (`backend/tests/integration/test_person_anonymise.py`,
  `backend/tests/integration/test_account_deletion.py`, over HTTP on a real Postgres):
  - Anonymisation: the stored row holds none of the seeded secrets, and the audit row holds none of
    the old values. Founder → anonymised → grandchild read đời 1, 2, 3 before and after.
  - Deletion: the identity fake receives `delete_user`, and the roles, claims and tokens are gone.
    The leftover token answers 403. The last admin is refused and nothing changes. A provider
    outage answers 503, and the same request then completes.
- **Negative controls, run 2026-11-28:**
  - soft-deleting the anonymised person's `parent_child` edges fails the đời test ("father is not
    reachable from the founder");
  - hard-deleting the profile row instead of tombstoning it fails the leftover-token test
    (`200 != 403`);
  - removing the last-admin check fails the refusal test.
- **A platform-deactivated account can delete itself.** `get_verified_token` skips the deactivation
  gate for this one route. This was judged acceptable: deletion removes data and grants nothing.
- **Known gaps, left open:**
  - Earlier `audit_logs` rows (`person.create` and `person.update` carry names and values) and
    earlier `change_requests` payloads still hold what an anonymisation clears. `audit_logs` is
    append-only for the request role (ADR-043), and its retention is ADR-030's.
  - Documents and events attached to an anonymised person are untouched; only the avatar is taken
    down.
  - The last super admin can delete their account; nothing stops a platform losing its last
    `super_admin`.
