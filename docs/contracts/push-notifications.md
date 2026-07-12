# Contract: push-notifications

## Type
FCM push contract (device tokens + message payloads)

## Owner
backend

## Consumers
- mobile
- web (if web push is enabled)

Verified against `app/services/scheduler.py`, `app/services/notification.py`,
`app/models/{notification_log,user_fcm_token}.py`, `app/api/v1/auth.py`, and
`app/infrastructure/persistence/auth_repository.py` as of 2026-07-12.

---

## 1. Token registration

- `POST /api/v1/auth/me/fcm-token` — Bearer required, no clan header.
  Body: `{"token": "<fcm token, max 500 chars>", "device_platform": "android"|"ios"|"web"}`
  → `{"data": {"message": "..."}}`.
  Storage semantics: `INSERT ... ON CONFLICT (token) DO UPDATE` — a token is globally
  unique (`user_fcm_tokens.token UNIQUE`); re-registering an existing token
  **re-binds it to the current user** and updates `device_platform`/`updated_at`.
- `DELETE /api/v1/auth/me/fcm-token` — same body shape; deletes the row matching
  the **current user + token** (deleting someone else's token is a no-op).

Client lifecycle: register after login and on FCM token rotation
(`onTokenRefresh`); `DELETE` the device's token before logout while the Bearer token
is still valid. See also `frontend-integration-guide.md` §7.

## 2. Notification types actually sent today

There is exactly **one** send path in the backend: the daily anniversary cron
(`scheduler.py::send_anniversary_notifications`, fires at `NOTIFICATION_CRON_HOUR`
= 07:00 `Asia/Ho_Chi_Minh` by default) → `notification.py::send_to_clan`. Verified:
`send_to_clan` / `send_push_notification` have **no other callers**.

A push is sent for an event when **all** of:

- `events.is_recurring = true`
- days until the next anniversary of `event_date` **equals** `notify_days_before`
  (0–30, default 7). For `events.is_lunar_calendar = false` the anniversary is the
  next solar month/day match; for `events.is_lunar_calendar = true` it is the next
  lunar anniversary converted to a solar date via the in-house Vietnamese lunar
  calendar engine (`app/services/lunar_calendar.py`, UTC+7 — see
  [ADR-018](../decisions/018-vietnamese-lunar-calendar.md)), applying the giỗ
  conventions (a leap-month death is observed in the regular month; lunar day 30
  clamps to day 29 in a short month). Both event sources are merged and fed
  through the same notify/dedup/commit loop — see
  `docs/architecture/notifications-scheduler.md`.
- the linked person (if any) is not soft-deleted
- no notification for the same event + type was already logged today (dedup via
  `notification_log`)

The notification type is the event's `event_type`
(`death_anniversary | birthday | wedding_anniversary | clan_ceremony | custom`), and
the title/body come from i18n keys `notification.{event_type}.title` / `.body`.
Translations exist **only** for `death_anniversary`, `birthday`, and
`wedding_anniversary` (all four locales). **⚠️ UNDEFINED — needs backend decision**:
a recurring `clan_ceremony` or `custom` event that matches the send conditions would
be pushed with the **raw i18n key** as its title/body (e.g.
`"notification.clan_ceremony.title"`), because `t()` falls back to the key when no
translation exists in any locale.

**Nothing else sends push today.** In particular there is **no** `claim_approved`,
membership-approved, invitation, or new-member notification — those flows emit domain
events for the audit log only. Do not build client handling for such types yet.

## 3. FCM message payload (as built in `notification.py`)

```python
messaging.Message(
    notification=messaging.Notification(title=..., body=...),  # localized text
    data={},                                                    # empty today
    token=<recipient token>,
    android=messaging.AndroidConfig(priority="normal"),
    apns=messaging.APNSConfig(payload=APNSPayload(aps=Aps(sound="default"))),
)
```

- **Localization: yes, per recipient.** `send_to_clan` selects every approved member
  of the event's clan who has ≥1 registered token, joined with
  `COALESCE(user_profiles.language, 'vi')`, and renders title/body with
  `t(key, locale=<that language>)`. `user_profiles.language` is synced from the JWT's
  `user_metadata.preferred_locale` on each authenticated request
  (`ensure_user_profile` in `app/core/security.py`), defaulting to `vi`.
- Title/body templates (verified in `app/i18n/*.json`), e.g. `en`:
  - `death_anniversary`: "Death anniversary" / "{name}'s death anniversary is in {days} days"
  - `birthday`: "Birthday" / "Today is {name}'s birthday"
  - `wedding_anniversary`: "Wedding anniversary" / "{name}'s wedding anniversary is in {days} days"
  - `{name}` is the linked person's `full_name`, falling back to the event `title`;
    `{days}` is `notify_days_before`.
- **`data` payload: empty.** The scheduler never passes a `data` dict, so the message
  carries no keys beyond the notification block.

## 4. Deep-link / tap-through

**No deep-link payload exists today** — `data` is `{}`, so the client cannot know
which event/person the notification refers to. Clients should open the app home (or
the events list) on tap. Adding `data` keys (e.g. `event_id`, `clan_id`,
`notification_type`) is a **backend TODO**; when added it will be an additive,
non-breaking change to this contract.

Note the multi-clan gap this implies: the notification belongs to a specific clan,
but the client has no way to switch to it on tap until a `clan_id` data key exists.

## 5. Invalid-token pruning

On `messaging.UnregisteredError` (FCM reports the token as no longer valid) the
backend **deletes that token row** (`DELETE FROM user_fcm_tokens WHERE token = ...`,
staged and committed with the scheduler's per-event transaction). Any other send
failure is logged and counted as failed; the token is kept. Consequence for clients:
a token can disappear server-side at any time — re-registering on every app start /
login (idempotent upsert) is the correct client behavior.

## 6. Delivery log (server-side only)

Every scheduler send attempt writes a `notification_log` row: `clan_id`, `event_id`,
`notification_type` (= event_type), `title` (the raw event title, not the localized
push title), `body` (empty string), `status` (`"sent"` if ≥1 device delivered, else
`"failed"`), `sent_at`, `error_message`. Broadcast rows use the zero UUID as
`user_id` (one row per event per day, not per recipient); the row doubles as the
daily dedup key.

**There is no client-facing notifications API** — no history, no read-state, no
preferences (see `rest-notifications-api.md`: the `/api/v1/notifications` stub was
removed). `notification_log` is not queryable by clients today.

## Versioning & Compatibility Rules
- Adding `data` payload keys or new notification types is additive/non-breaking, but
  new types must ship with i18n keys in all four locales (see §2 gap).
- Changing token registration semantics or the notification block structure is
  breaking for mobile releases in the field.
- Keep this file in sync with `scheduler.py`/`notification.py` — it documents actual
  send behavior, not aspirations.
