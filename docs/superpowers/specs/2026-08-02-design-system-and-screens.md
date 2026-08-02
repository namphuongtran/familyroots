# Design System & Screen Specification — Arbor Heritage (web + mobile)

## Type
Design specification (product design; no application code)

## Date
2026-08-02

## Owner
Product design

## Consumers
- web (Next.js 16 / React 19 / Tailwind v4 `@theme`)
- mobile (Flutter / `ThemeExtension`)

## Status
Proposed. This document **extends** the Arbor Heritage mandates in `mobile/CLAUDE.md`
and the repo-root `CLAUDE.md`; it does not replace them. Where this document and
those mandates disagree, the mandates win and this document is the bug.

---

## 0. Scope and sources of truth

| Concern | Source of truth | This doc's job |
|---|---|---|
| Design mandates (no-line rule, faces, radii, glass, ambient depth, never `#000000`) | `mobile/CLAUDE.md` § Arbor Heritage | Obey and extend into a full token set |
| đời / đa thê / pedigree collapse / thủy tổ | `docs/architecture/tree-read-model.md` | Turn into rendering rules |
| Domain invariants, Vietnamese glossary | `docs/architecture/domain-rules.md` | Turn into form validation + copy |
| `HistoricalDate`, envelope, cursor pagination | `docs/contracts/README.md` | Turn into date/list presentation rules |
| Real client states (pending, suspended, unverified, multi-clan, `clan_founder_not_found`) | `docs/contracts/frontend-integration-guide.md` | Turn into screens, not error toasts |
| Role affordances | `docs/architecture/rbac.md` | Turn into per-role UI rules |

**Non-goals.** No component code, no route changes, no contract changes. Nothing here
asks the backend for a new endpoint; where the design wants one that does not exist, it
is filed in §9 as an open question and the design ships without it.

---

## 1. Who we design for — the constraints, restated as rules

The clan is the user, not a segment of the clan. A 19-year-old on a flagship and a
78-year-old trưởng họ on a five-year-old Android on weak 3G are both first-class. That
produces six hard rules that every screen in §7 is checked against:

1. **`vi` is the design locale.** Layouts are composed and reviewed in Vietnamese with
   full diacritics first. English is the translation, not the source. Vietnamese runs
   roughly 10–25% longer than English and its diacritic stacks are taller — nothing may
   be sized from an English string.
2. **Body text starts at 17px / 17sp.** Not 14, not 16. `body-lg` is the default, and
   `body-sm` (14) is never used for content a user must read to act.
3. **Every screen survives 200% OS text scale** at 320 dp width with no clipping and no
   overlap. Fixed heights on anything containing text are forbidden.
4. **Nothing depends on hover** and nothing depends on an image loading. Avatars are
   initials by default and photographs are an enhancement.
5. **Weak network is the normal case.** Shape-matched skeletons, reserved space (zero
   layout shift), explicit retry, and an honest offline state — never an infinite
   spinner.
6. **Contrast floor is WCAG AA and it is enforced at the token level** (§6), so a
   designer cannot accidentally ship an unreadable pairing.

---

## 2. Design tokens

Tokens are expressed as **semantic roles**, never as raw colour names. A component
never references "green" or "red"; it references `primary` or `danger`. This is what
lets the same component tree render both themes and a future high-contrast mode.

Naming follows Material 3 role naming, because `mobile/CLAUDE.md` already speaks it
(`on_surface`, `surface-container-low`, `outline_variant`). Web uses the same names in
kebab-case; Flutter uses the same names in lowerCamelCase.

### 2.1 Colour — light theme (default)

**Surfaces.** The no-line rule means boundaries are *background steps*, so we need more
surface levels than a bordered system would.

| Token | Value | Use |
|---|---|---|
| `surface` | `#FBF8F1` | Page ground (warm paper) |
| `surface-container-lowest` | `#FFFDF9` | Cards that must lift off the page |
| `surface-container-low` | `#F4EFE4` | Default card / field fill |
| `surface-container` | `#EDE6D7` | Grouped rows, list section grounds |
| `surface-container-high` | `#E5DBC8` | Hovered/pressed container, selected row |
| `surface-container-highest` | `#DCD1BA` | Pressed state, scrubber tracks |
| `on-surface` | `#1D1B16` | Primary text (**mandated**; never `#000000`) |
| `on-surface-variant` | `#57503F` | Secondary text, icons |
| `on-surface-muted` | `#6E6653` | Tertiary text, timestamps, helper text |
| `outline-variant` | `#B3A98F` | **Only** in high-contrast mode, at 15% opacity |
| `scrim` | `rgba(29,27,22,0.44)` | Behind dialogs/sheets |

**Interactive — leaf (the arbor).**

| Token | Value | Use |
|---|---|---|
| `primary` | `#3E5C38` | Primary actions, active nav, links |
| `on-primary` | `#FFFFFF` | Text/icon on `primary` |
| `primary-container` | `#D6E4CE` | Tonal buttons, selected chips |
| `on-primary-container` | `#14260F` | Text on `primary-container` |
| `secondary` | `#7A6248` | Secondary actions, bark accents |
| `secondary-container` | `#EADDCB` | Quiet tonal surfaces |
| `on-secondary-container` | `#2A2013` | Text on `secondary-container` |

**Ceremonial — lacquer & gilt.** Reserved. See §9-J1 for why this is a separate family
from `primary`.

| Token | Value | Use |
|---|---|---|
| `heritage` | `#A3182F` | Thủy tổ marker, giỗ (death anniversary), ancestral emphasis |
| `on-heritage` | `#FFFFFF` | Text on `heritage` |
| `heritage-container` | `#F6DFE0` | Giỗ chips, thủy tổ card ground |
| `on-heritage-container` | `#4A0A14` | Text on `heritage-container` |
| `gilt` | `#8A6A16` | Gold **text/icons** (contrast-safe) |
| `gilt-decor` | `#D4AF37` | Gold **fills, strokes, rules only** — never text |

**Semantic status.** Separate from both accent families; status is never carried by the
brand hue.

| Token | Value | Container | On-container |
|---|---|---|---|
| `success` | `#2E6A4E` | `#D5E9DC` | `#0C2A1B` |
| `warning` | `#8A5A00` | `#F8E6C6` | `#3A2400` |
| `danger` | `#A32218` | `#F8DED9` | `#410B06` |
| `info` | `#2A5A78` | `#D8E7F0` | `#0A2433` |

**Focus.** `focus-ring: #1D1B16` (light) / `#F1EBDE` (dark) — the on-surface colour, at
3px with a 2px `surface`-coloured offset. Using on-surface rather than an accent
guarantees ≥3:1 against every ground in the system, including `primary` and `heritage`
fills.

### 2.2 Colour — dark theme

Not an inversion. Ground is warm ink, never `#000000`; the leaf lifts, the lacquer
desaturates so it does not vibrate on dark.

| Token | Value | | Token | Value |
|---|---|---|---|---|
| `surface` | `#15140F` | | `primary` | `#A3C398` |
| `surface-container-lowest` | `#100F0B` | | `on-primary` | `#12280D` |
| `surface-container-low` | `#1D1B15` | | `primary-container` | `#2B4526` |
| `surface-container` | `#24221A` | | `on-primary-container` | `#CBE3C2` |
| `surface-container-high` | `#2D2A20` | | `secondary` | `#D3BC9E` |
| `surface-container-highest` | `#383426` | | `secondary-container` | `#4A3A27` |
| `on-surface` | `#F1EBDE` | | `heritage` | `#F0A0A8` |
| `on-surface-variant` | `#C6BDA8` | | `heritage-container` | `#4E1520` |
| `on-surface-muted` | `#A99F89` | | `on-heritage-container` | `#FFD9DC` |
| `outline-variant` | `#6E6653` | | `gilt` | `#E3C464` |
| `scrim` | `rgba(8,7,5,0.62)` | | `gilt-decor` | `#D4AF37` |

Status on dark: `success #8FCFAA` / `#1B3A2A`, `warning #E8B563` / `#3E2A06`,
`danger #F0A79C` / `#4A1811`, `info #9CC8E4` / `#12303F`.

Shadow colour on dark is `rgba(8,7,5,0.55)` — a near-ink, not pure black.

### 2.3 Type scale

Faces are mandated: **Plus Jakarta Sans** (headings, display, person names, branch
titles, milestones) and **Manrope** (body, labels, data). No system-font fallback.

| Token | Face | Size | Line height | Weight | Tracking | Use |
|---|---|---|---|---|---|---|
| `display-lg` | Jakarta | 40 | 48 (1.20) | 800 | −0.02em | Screen hero on desktop only |
| `display-md` | Jakarta | 32 | 40 (1.25) | 700 | −0.015em | Page title |
| `headline` | Jakarta | 26 | 34 (1.31) | 700 | −0.01em | Section head, person name on profile |
| `title-lg` | Jakarta | 21 | 30 (1.43) | 600 | 0 | Card title, person name in tree node |
| `title-md` | Jakarta | 18 | 26 (1.44) | 600 | 0 | List row name, dialog title |
| `body-lg` | Manrope | 17 | 28 (1.65) | 400 | 0 | **Default body** |
| `body-md` | Manrope | 15 | 24 (1.60) | 400 | 0 | Dense metadata, table cells |
| `body-sm` | Manrope | 14 | 22 (1.57) | 400 | 0 | Captions only — never load-bearing |
| `label-lg` | Manrope | 16 | 22 (1.38) | 600 | +0.005em | Button text |
| `label-md` | Manrope | 14 | 20 (1.43) | 600 | +0.01em | Chips, badges, field labels |
| `overline` | Manrope | 12 | 16 (1.33) | 700 | +0.08em | Eyebrow labels — see caps rule below |
| `numeric` | Manrope | inherit | inherit | inherit | 0 | `font-variant-numeric: tabular-nums` |

**Vietnamese typography rules (binding):**

- Minimum line-height ratio is **1.20 for display, 1.30 for titles, 1.55 for body**.
  Vietnamese stacks two marks (`ế`, `ộ`, `ữ`) and a tighter leading collides them with
  the descenders of the line above.
- **`overline` may only be set in caps for words with no tone marks.** `THÀNH VIÊN`
  loses its diacritics to optical crowding at 12px; use sentence case (`Thành viên`)
  with the same tracking instead. Caps is available for `ĐỜI`, `GIỖ`, short ASCII.
- Never `text-transform: uppercase` on user data (names, place names, biographies).
- Person names are always Jakarta, never Manrope, at every size — a name is a heading
  wherever it appears.
- `tabular-nums` on every column of years, đời numbers, counts, and dates.

### 2.4 Spacing

4px base, geometric-ish ramp. Both clients use the same numbers (px on web, logical px
in Flutter).

`space-1` 4 · `space-2` 8 · `space-3` 12 · `space-4` 16 · `space-5` 20 · `space-6` 24 ·
`space-8` 32 · `space-10` 40 · `space-12` 48 · `space-16` 64 · `space-20` 80 ·
`space-24` 96

Applied defaults: screen gutter `space-5` (mobile) / `space-8` (desktop); card padding
`space-5`; gap between stacked cards `space-4`; section gap `space-10`; gap between two
adjacent tap targets ≥ `space-2`.

**Layout, not margins.** Sibling groups are laid out with flex/grid `gap`, never with
per-child margins — margins collapse and double under 200% text scale and produce the
uneven rhythm this system is trying to avoid.

### 2.5 Radii

Mandated: `9999px` for primary buttons, `2rem` for nodes, never `sm`/`none`.

`radius-xs` 8 (chips, badges) · `radius-sm` 12 (inputs, small cards) ·
`radius-md` 16 (cards) · `radius-lg` 20 (panels) · `radius-xl` 28 (dialogs, sheets —
top corners only for bottom sheets) · `radius-node` 32 (tree nodes, person cards) ·
`radius-pill` 9999 (buttons, chips-as-buttons, avatars)

**Floor: 8.** Nothing in the system is squarer than `radius-xs`. Full-bleed images
inside a card inherit the card's inner radius (`radius − padding`), never square off.

### 2.6 Elevation and glass

Ambient depth only — no rigid drop shadows, no hard offsets.

| Token | Light | Use |
|---|---|---|
| `elev-0` | none | Flat content on `surface` |
| `elev-1` | `0 1px 2px rgba(29,27,22,.03), 0 8px 24px rgba(29,27,22,.04)` | Resting card |
| `elev-2` | `0 2px 4px rgba(29,27,22,.03), 0 16px 32px rgba(29,27,22,.06)` | Hover/raised (the mandate's 32px @ 6%) |
| `elev-3` | `0 4px 8px rgba(29,27,22,.04), 0 32px 64px rgba(29,27,22,.10)` | Dialog, bottom sheet, dragged node |

**Glass** (floating nav bars, the tree's floating toolbar, the mobile bottom bar):
background = `surface` at **80% opacity**, `backdrop-filter: blur(20px) saturate(1.08)`.
Flutter equivalent is `BackdropFilter(ImageFilter.blur(sigmaX: 10, sigmaY: 10))` —
CSS blur radius ≈ 2 × Gaussian sigma, so 20px CSS = sigma 10.

**Glass fallback is mandatory.** On devices without backdrop-filter support, and
whenever the device reports reduced transparency or low power, glass degrades to an
opaque `surface-container-low`. A five-year-old Android must not pay a per-frame blur
for a scrolling list. Rule: glass is used on **at most one persistent surface per
screen**.

### 2.7 Motion

| Token | Duration | Use |
|---|---|---|
| `dur-1` | 90ms | Press/release, checkbox, chip toggle |
| `dur-2` | 160ms | Hover, focus ring, small fades |
| `dur-3` | 240ms | Card enter/exit, tab change, expand |
| `dur-4` | 380ms | Dialog, bottom sheet, route transition |
| `dur-5` | 600ms | Tree pan/zoom-to-node, ambient |

Easing: `ease-standard cubic-bezier(.2,0,0,1)` · `ease-decelerate cubic-bezier(.05,.7,.1,1)`
(entering) · `ease-accelerate cubic-bezier(.3,0,.8,.15)` (exiting).

**Reduced motion** (`prefers-reduced-motion` / `MediaQuery.disableAnimations`): all
transforms become instant; opacity transitions are capped at 90ms; the tree never
auto-pans, it jumps; skeleton shimmer becomes a static tint.

### 2.8 Expressing tokens in both clients

The token set is deliberately flat name→value so it maps 1:1 onto both platforms.
These are spec illustrations, not code to copy into the app.

Web — Tailwind v4 `@theme`:

```
@theme {
  --color-surface: #FBF8F1;
  --color-surface-container-low: #F4EFE4;
  --color-on-surface: #1D1B16;
  --color-primary: #3E5C38;
  --color-heritage: #A3182F;
  --text-body-lg: 17px;
  --text-body-lg--line-height: 28px;
  --spacing-5: 20px;
  --radius-node: 32px;
  --shadow-elev-2: 0 2px 4px rgb(29 27 22 / .03), 0 16px 32px rgb(29 27 22 / .06);
}
```

Dark theme redefines only the `--color-*` group under
`@media (prefers-color-scheme: dark)` **and** `:root[data-theme="dark"]`; components
never branch on theme themselves.

Flutter — one `ThemeExtension` per token family (`ArborColors`, `ArborType`,
`ArborSpace`, `ArborShape`, `ArborElevation`, `ArborMotion`), each with `copyWith` and
`lerp`, registered on both `ThemeData.light()` and `.dark()`. Widgets read
`Theme.of(context).extension<ArborColors>()!.heritage` — never a `const Color` literal.
`ColorScheme` is populated from the same values so Material widgets inherit correctly.

---

## 3. Domain presentation primitives

These are the rules that make this a gia phả and not a CRUD app. They are shared
behaviour, specified once, implemented in both clients.

### 3.1 `HistoricalDate` — the five precisions

Every genealogical date arrives as `{date, precision, display, lunar}`. There is exactly
one renderer, `<HistoricalDate>` / `ArborDate`, and no screen formats a date itself.

| `precision` | Renders | Precision affordance | Example |
|---|---|---|---|
| `exact` | `date` formatted `dd/MM/yyyy` | none | `15/08/1948` |
| `year` | `display`, falling back to the year of `date` | chip `năm` | `1948` + `năm` |
| `month` | `display`, falling back to `MM/yyyy` | chip `tháng` | `08/1948` + `tháng` |
| `circa` | `display`, falling back to `khoảng {year}` | chip `khoảng` | `khoảng 1750` + `khoảng` |
| `unknown` | `Không rõ` | chip `không rõ` | `Không rõ` |

Rules:

- **Never invent precision.** If `precision != "exact"`, the exact `date` value is never
  shown to the user, even though the API sends one (it exists for sorting and
  anniversaries only).
- **The precision chip is text, not colour.** `label-md`, `on-surface-variant` on
  `surface-container`, `radius-xs`. Estimated dates are not warnings — a 300-year-old
  record being approximate is normal and must not look like an error.
- **Lunar is a second line, never inline.** When `lunar` is non-null it renders below
  the solar line as `Âm lịch · 15/08 Nhâm Tý` in `body-md` / `on-surface-muted`. It is
  never merged into the solar string and never parsed.
- **`lunar` is user-entered text and is returned verbatim in every locale.** It is not
  translated, not reformatted, not validated against a calendar. See §9-J7.
- **Unknown is a first-class value, not an empty state.** A person with
  `precision: "unknown"` on both dates is a complete, valid record. The profile shows
  `Không rõ`, not a blank or a dash.
- Screen readers announce the rendered string plus, when present, `âm lịch, …`.

### 3.2 đời (generation) badge

`generation` comes from one backend authority (`con theo đời cha`) and **can legitimately
be `null`**.

- Present: `Đời {n}` — `label-md`, `on-heritage-container` on `heritage-container`,
  `radius-pill`, `tabular-nums`. đời is lineage, so it wears the ceremonial family.
- Null: **`Đời ?`** — `on-surface-variant` on `surface-container-high`, same shape. Never
  omitted, never guessed, never rendered as `Đời 0` or `Đời —`.
- `Đời ?` is tappable/focusable and opens a one-paragraph explainer:
  *"Chưa xác định được đời vì người này chưa nối được với thủy tổ của dòng họ. Khi quan
  hệ cha/mẹ được bổ sung, hệ thống sẽ tự tính lại."* Admins additionally get
  `Nối vào cây` → the relationship editor.
- Screen reader: `đời thứ 5` / `chưa xác định đời`.
- Sorting: null-đời **never** sorts as 0 or ∞ into the numeric run. Lists group them
  under an explicit `Chưa xác định đời` section at the end.

### 3.3 đa thê — grouping children by wife

A father's children are grouped under each wife via `mother_id` and
`mother_spouse_order`.

- Each group has a **WifeGroupHeader**: the wife's name in `title-md` (Jakarta) plus an
  order chip from `mother_spouse_order`: `1 → Vợ cả`, `2 → Vợ hai`, `3 → Vợ ba`,
  `n → Vợ thứ {n}`.
- `mother_spouse_order == null` but `mother_id` present → header shows the wife's name
  with no order chip. Order is a fact from the marriage record; absence of it is not
  "first".
- `mother_id == null` → the child appears in a final ungrouped section headed
  `Chưa rõ mẹ`. Not "Khác", not silently folded into the first wife.
- Groups are ordered by `spouse_order` ascending, `null` last, then `Chưa rõ mẹ`.
- The group header is **background-shifted, never ruled**: children of one wife sit on
  `surface-container-low` inset from `surface`, with `space-4` between groups. This is
  exactly the case the no-1px-border rule exists for.
- One wife's children are never visually subordinate to another's. Same node size, same
  type, same treatment; only the header differs.

### 3.4 Pedigree collapse stubs

A node with `pedigree_collapse_ref: true` displays but does not descend. Its
`children`/`spouses` are forced empty, and its `has_more_descendants` may still be
`true` — so the two fields disagree by design.

- Render the **full node** (same size, same name, same đời badge) plus a chip:
  `Nhánh chính ở nơi khác`.
- Replace the expand chevron with `Xem ở nhánh chính →`, which navigates to the
  canonical occurrence. **Never render an expand affordance on a stub**, regardless of
  `has_more_descendants` — an expander that yields nothing is the worst possible
  outcome on a weak network.
- Never grey a stub. Grey means deleted or inactive; this person is neither.
- Screen reader appends: `xuất hiện ở nhiều nhánh; nhánh chính ở nơi khác`.

### 3.5 Role → affordance

Three clan roles. The rule is **remove, do not disable**.

| Surface | admin | editor | viewer |
|---|---|---|---|
| Person profile header | `Sửa`, `Xóa`, `⋯` | `Sửa` | *(no buttons)* |
| Member list | `+ Thêm thành viên` FAB | `+ Thêm thành viên` FAB | *(no FAB)* |
| Tree node long-press sheet | Xem · Sửa · Thêm con · Thêm vợ/chồng · Đặt thủy tổ | Xem · Sửa · Thêm con · Thêm vợ/chồng | Xem hồ sơ · Tìm quan hệ |
| `clan_founder_not_found` | `Chọn thủy tổ` CTA | read-only explainer | read-only explainer |
| Events | tạo/sửa/xóa | tạo/sửa/xóa | *(no buttons)* |
| Documents | tải lên, xóa | tải lên | *(no buttons)* |
| Admin nav item | visible | hidden | hidden |

A viewer sees **zero disabled controls**. A screen full of greyed buttons reads as
"broken" to a non-technical user and as "you are not trusted" to a family member.
Instead, the profile header carries one quiet, permanent line in `body-md` /
`on-surface-muted`:

> Bạn đang xem gia phả với quyền **Người xem**. Để bổ sung hoặc sửa thông tin, xin liên
> hệ quản trị dòng họ.

with `Xem danh sách quản trị` as a text link. See §9-J5 — the honest fix is a
change-request feature that does not exist yet.

### 3.6 Error code → UI state

Global rule: **switch on `error.code`, display `error.message`** (the backend localises
it). Codes below get a designed state; anything else falls through to the generic
`ErrorState`.

| Code | HTTP | UI |
|---|---|---|
| `email_not_verified` | 403 | Full screen: xác thực email + resend (§7.1c) |
| `account_deactivated` | 403 | Full screen block, sign out |
| `clan_suspended` | 403 | Full screen block + clan switcher if other clans (§7.2c) |
| `no_approved_clan_membership` | 403 | Route to pending or onboarding (§7.2a) |
| `multiple_clans_no_selection` | 400 | Clan picker (§7.2b) |
| `clan_founder_not_found` | 404 | **Onboarding state on the tree screen** (§7.4b) — never an error screen |
| `stale_write` | 409 | Conflict dialog (§7.7c) |
| `invalid_cursor` | 400 | Silent: drop cursor, refetch page 1, keep scroll |
| `rate_limited` | 429 | Inline countdown from `detail.retry_after`; disable submit |
| `auth_provider_unavailable`, `storage_unavailable` | 503 | Transient banner + retry — **never** "sai mật khẩu" |
| `relationship.parent_too_young` | 422 | Inline field error on the parent field |
| `meta.warning` on a 2xx | — | Non-blocking toast after success, never a blocker |

---

## 4. Component inventory

Every component below is specified for **default · hover · pressed · focus · disabled ·
loading · empty · error**, with the understanding that not every state applies to every
component (a button has no empty state; a list has no pressed state). "—" means the
state does not exist for that component and must not be invented.

### 4.1 Actions

**Button** — variants `primary` (filled `primary`), `tonal` (`primary-container`),
`ghost` (transparent, `primary` text), `danger` (filled `danger`), `heritage` (filled
`heritage`, reserved for ceremonial actions like `Đặt làm thủy tổ`). Sizes: `lg` 56dp,
`md` 48dp, `sm` 40dp (web pointer only). Always `radius-pill`, `label-lg`, horizontal
padding `space-6`.

| State | Treatment |
|---|---|
| default | Fill per variant, `elev-0` |
| hover (web) | Fill darkened 6% (light) / lightened 8% (dark), `elev-1`, `dur-2` |
| pressed | Fill darkened 12%, scale 0.98, `dur-1` |
| focus | 3px `focus-ring` + 2px offset, retained on `:focus-visible` and always on keyboard |
| disabled | `on-surface` @ 12% fill, `on-surface` @ 38% label, no shadow, `cursor: not-allowed`. **Reserve for transient states only** (form invalid, submitting) — never for permission (§3.5) |
| loading | Label stays in place, opacity 0.6; 20dp indeterminate ring replaces the leading icon slot; width does not change; `aria-busy`, `aria-live="polite"` announces `Đang lưu…` |

**IconButton** — 48dp mobile / 44px web, `radius-pill`, icon 24dp. Always has an
accessible name. Never the only carrier of a destructive action.

**FAB (mobile)** — 64dp, `primary`, `radius-pill`, `elev-2`, bottom-right above the
glass nav bar, respects safe area. Extends to a labelled pill (`+ Thêm thành viên`) on
first paint of an empty list, collapses to icon on scroll.

### 4.2 Inputs

**TextField** — filled: `surface-container-low`, `radius-sm`, min-height 56dp, label
**above** the field in `label-md` (not floating — floating labels shrink to ~11px and
Vietnamese diacritics disappear), helper text below in `body-md`.

| State | Treatment |
|---|---|
| default | `surface-container-low` fill, `on-surface` text, placeholder `on-surface-muted` |
| hover (web) | fill → `surface-container` |
| focus | 3px `focus-ring`, fill → `surface-container-lowest` |
| disabled | fill `on-surface` @ 6%, text @ 38%, label unchanged |
| read-only | fill `surface-container`, no ring, value selectable |
| error | fill `danger-container`, message below in `on-danger-container` **with an alert icon**, `aria-describedby`, `aria-invalid` |
| loading (async validate) | 20dp ring in the suffix slot; field stays editable |

No underline, no 1px outline, in any state. The focus ring is an accessibility
affordance and is explicitly exempt from the no-line rule (§9-J2).

**HistoricalDateField** — the composite that makes this product possible. Layout, top to
bottom:

1. Label (`Ngày sinh`).
2. Precision **SegmentedControl**: `Chính xác · Tháng · Năm · Khoảng · Không rõ`. Wraps
   to two rows under 200% text scale; never scrolls horizontally.
3. Conditional value area:
   - `Chính xác` → three `tabular-nums` fields `Ngày / Tháng / Năm` (not a calendar
     popover — a 1780 date is 240 taps away in a month picker), plus an optional native
     picker button for recent dates.
   - `Tháng` → `Tháng / Năm`. `Năm` → `Năm`. `Khoảng` → `Năm` + free-text `Cách ghi`
     prefilled `khoảng {năm}`. `Không rõ` → value area collapses entirely.
4. Optional `Ngày âm lịch (ghi trong gia phả)` free-text field, always available,
   helper: *"Ghi đúng như trong gia phả, ví dụ: 15/08 Nhâm Tý. Hệ thống không tự quy
   đổi."*
5. Live preview line showing exactly what the profile will display.

**Select**, **Checkbox** (24dp box / 48dp target), **Radio**, **Switch** (52×32 track) —
standard states; all carry a text label, never icon-only.

**SearchField** — `radius-pill`, leading search icon, trailing clear (appears only when
non-empty), 300ms debounce, `role="searchbox"`, results count announced politely.
Loading = 20dp ring replacing the clear button; the previous result list stays visible
and dims to 0.6 rather than being replaced by skeletons (avoids the flash-of-empty on
every keystroke over 3G).

### 4.3 Display

**Chip** — `label-md`, `radius-pill`, height 32 (display) / 40 (interactive). Kinds:
`neutral` (`surface-container` / `on-surface-variant`), `generation`
(`heritage-container`), `role`, `precision`, `status`, `filter` (selected =
`primary-container` + check icon — selection is never colour-only).

**Avatar** — `radius-pill`. **Initials are the default rendering**, not the fallback:
first letter of the last given name, `title-md` Jakarta on a tint deterministically
derived from the person id (six approved tints from the `secondary`/`primary` families,
all ≥4.5:1 against `on-surface`). A photo overlays it only after it loads. On image
error the initials are already there — no layout shift, no broken-image icon. Sizes 32 /
40 / 56 / 96. `alt` = the person's full name; when initials-only, the visual is
`aria-hidden` and the name is read from the adjacent text.

**PersonNodeCard** (tree) — `radius-node` (32), `surface-container-low`, `elev-1`,
padding `space-4`, min-width 200 / max-width 280. Contents: avatar 40, name
`title-lg` Jakarta (two lines max, ellipsis with full name in the sheet), đời badge,
life line (`1892 – khoảng 1961`) in `body-md` `tabular-nums`, and at most one status
chip. Thủy tổ nodes get a `heritage-container` ground plus a `Thủy tổ` chip in
`heritage`. Deceased is indicated by the death date's presence, not by greying.

States: default · hover `elev-2` + `surface-container` (web) · pressed scale 0.99 ·
focus 3px ring · selected `primary-container` ground + 3px `primary` ring · loading
skeleton of the identical shape · error (node failed to load) shows the id and a retry.

**ListRow / PersonRow** — min-height 72dp, avatar 40, name `title-md`, secondary line
`body-md` `on-surface-variant`, trailing đời badge. Rows are separated by **background
alternation is forbidden** (zebra striping is a rule by another name); separation comes
from `space-2` gaps and each row sitting on `surface-container-low` over `surface`.

**Banner** — inline, `radius-md`, tonal container per kind (`info`, `warning`, `danger`,
`success`, `heritage` for onboarding), leading icon, `body-lg` message, optional action
as a `ghost` button. Dismissible banners persist their dismissal per user per clan.

**EmptyState** — no illustration (an image that may not load cannot carry the message).
Typographic: `headline` line, `body-lg` explanation of *why* it is empty and *what
happens next*, one primary action if the role allows one, otherwise nothing. Never
"Không có dữ liệu".

**ErrorState** — `headline` in plain Vietnamese describing what failed,
`error.message` from the envelope in `body-lg`, `Thử lại` primary button, and
`error.code` in `body-sm` `on-surface-muted` (copyable — the trưởng họ will read it to
whoever helps them).

**Skeleton** — shape-matched to the real content, `surface-container` with a
`surface-container-high` sweep over `dur-5`, static tint under reduced motion. Skeletons
must occupy the **exact** final geometry: list skeletons render the real row height, the
tree renders node-shaped blocks in the real layout. Zero CLS is a pass/fail criterion
(§6, T-09).

**OfflineBar** — persistent, glass-free, `warning-container`, above the nav:
*"Đang mất kết nối. Dữ liệu bạn đang xem là bản đã lưu lúc {giờ}."*

### 4.4 Navigation and overlays

**AppBar (mobile)** — glass, 56dp + safe area, title `title-lg`, back as a 48dp icon
button, at most two trailing actions (overflow the rest).

**BottomNav (mobile)** — glass, 5 items: `Tổng quan · Cây gia phả · Thành viên · Sự
kiện · Tài khoản`. Icon 24 + label `label-md` **always visible** (icon-only nav is
unusable for an older first-time user). Active = `primary` icon + label + a
`primary-container` pill behind the icon. Height grows with text scale; labels wrap to
two lines rather than truncate.

**Sidebar (web)** — 264px, `surface-container-low`, collapsible to 72px icon rail above
1280px only; below 1024px it becomes a drawer. Clan switcher pinned at the top, user
menu at the bottom.

**ClanSwitcher** — shows clan name + role chip. Single-clan users see it as static text,
not a control. Multi-clan users get a menu; switching is a full state reset (query cache
cleared) with a `dur-4` cross-fade, because showing clan A's tree with clan B's header
for even one frame is a data-integrity failure in this product.

**BottomSheet (mobile)** / **SidePanel (web ≥1024px)** — the same content, presented per
platform. `radius-xl` top corners, `elev-3`, drag handle, scrim, focus trap, Esc /
back-gesture to close.

**Dialog** — max-width 480, `radius-xl`, `elev-3`, title `title-lg`, body `body-lg`,
actions right-aligned on web / full-width stacked on mobile, destructive action never
the default focus.

**Toast** — bottom-centre above the nav, `surface-container-highest`, `radius-pill`,
`elev-2`, 5s (never auto-dismisses an error), one action slot, `role="status"`.

**Tabs** — text labels, `title-md`, active indicator is a 3px `primary` bar (an active
indicator is a control affordance, not a section rule — exempt), scrollable when
overflowing, never truncating a Vietnamese label.

**Tooltip** — **web pointer only**. Every tooltip's content must also be reachable
without hover (a `⋯` sheet, helper text, or an info button). Mobile has no tooltips.

### 4.5 Domain components

- **GenerationBadge** — §3.2.
- **HistoricalDateDisplay** — §3.1.
- **WifeGroupHeader** — §3.3.
- **PedigreeStubChip** — §3.4.
- **FounderPrompt** — §7.4b.
- **ConflictDialog** — §7.7c.
- **RelationshipRow** — kinship term (server-localised) + person + type chip
  (`Con đẻ` / `Con nuôi` / `Con riêng`) + date range.
- **LunarLine** — §3.1.
- **CursorList** — the only list primitive. Owns: first-page skeleton, empty, error,
  `Tải thêm`, end-of-list marker, and `invalid_cursor` recovery. No screen implements
  pagination itself.

---

## 5. Accessibility — testable requirements

Each is written so a person or a test can return pass/fail. These are release gates, not
aspirations.

| # | Requirement | Pass criteria |
|---|---|---|
| T-01 | Text contrast | Every text/background token pair used in the build measures ≥4.5:1, or ≥3:1 for text ≥24px or ≥19px bold. Verified by a token-pair audit script over the approved pairs list, not by spot-checking screenshots. |
| T-02 | Non-text contrast | Focus rings, selected-state indicators, and input fills measure ≥3:1 against adjacent colours. |
| T-03 | Touch targets | Every interactive element's hit box is ≥48×48dp on mobile and ≥44×44px on web pointer, including icon buttons, chips, and list-row trailing actions. Adjacent targets have ≥8dp separation. |
| T-04 | 200% text scale | Every screen in §7 renders at 320dp width with OS text scale 2.0 (web: root font-size 32px, plus 200% browser zoom) with **no clipped glyph, no overlapping element, and no horizontal page scroll**. Captured as a screenshot set per release. |
| T-05 | No fixed heights on text | No container holding user text or a localised string declares a fixed height. Enforceable by lint/grep in review. |
| T-06 | Colour is never the only channel | Every state (selected, error, precision, role, deceased, stub) carries text or an icon in addition to colour. Verified by rendering the screen set in greyscale and confirming every state is still identifiable. |
| T-07 | Keyboard operability | Every action is reachable and executable by keyboard alone, in a logical order, with a visible focus ring at every stop. **Includes the family tree** — see T-08. |
| T-08 | Tree has an accessible equivalent | The pan/zoom tree canvas is accompanied by a keyboard-navigable, screen-reader-readable list/outline view exposing the same nodes, đời values, and đa thê grouping. Toggle is visible, not hidden in settings. |
| T-09 | Zero layout shift | Cumulative Layout Shift ≤ 0.02 on every route, measured on a throttled 3G profile. Skeletons must match final geometry. |
| T-10 | No hover-only information | With a pointer-less profile, every piece of information and every action remains reachable. |
| T-11 | Reduced motion | With `prefers-reduced-motion: reduce`, no element translates or scales; opacity transitions ≤90ms; the tree does not auto-pan. |
| T-12 | Language announcement | The document/app declares `lang="vi"` (or the active locale) so diacritics are pronounced correctly; any element whose content is in a different language carries its own `lang`. |
| T-13 | Form semantics | Every field has a programmatically associated label; errors are referenced by `aria-describedby` and announced; on failed submit, focus moves to the first invalid field and a summary is announced once. |
| T-14 | đời announcement | `Đời 5` announces as "đời thứ 5"; `Đời ?` announces as "chưa xác định đời". Never a bare number, never "question mark". |
| T-15 | Date announcement | A `HistoricalDate` announces its display string, and appends "âm lịch, {lunar}" when a lunar value exists. `unknown` announces "không rõ", not silence. |
| T-16 | Images are optional | With all image requests blocked, every screen remains fully usable and no layout changes size. Avatars show initials; documents show type + filename. |
| T-17 | Error recovery is always offered | Every error state exposes a retry or an alternative next step; no dead-end screens. |
| T-18 | Timing | No auto-advancing carousel, no auto-dismissing error, no session-expiry without warning. |

---

## 6. Layout system

**Mobile (Flutter)** — single column. Content width = screen − 2×`space-5`. Breakpoint
at 600dp switches to a two-column split on tablets (list + detail). Safe areas
respected top and bottom; the glass nav bar's height is added to every scroll view's
bottom padding.

**Web** — content max-width **1200px**, centred, gutters `space-8`.

| Breakpoint | Layout |
|---|---|
| < 640 | Single column, drawer nav, mobile-equivalent screens |
| 640–1023 | Single column, wider gutters, drawer nav |
| 1024–1279 | Sidebar 264 + single content column |
| ≥ 1280 | Sidebar 264 + content, detail screens may use a 2-column split (main 1fr / aside 360) |

Grids are used only where the data is genuinely tabular (member list at ≥1024, admin
approval queue). Everywhere else layout is asymmetric flow per the mandate — the
dashboard is a deliberate two-size card flow, not a uniform 3×N grid.

---

## 7. Screen specifications

Notation per screen: **Purpose · Mobile · Desktop · States · Role · API**.

---

### 7.1 Đăng nhập / Đăng ký / Xác thực email

#### 7.1a Đăng nhập

**Purpose.** Get an existing family member into their clan in as few taps as possible,
and route them correctly afterwards.

**Mobile.** Vertically centred single column, gutters `space-5`. Top: clan-agnostic
wordmark (type only — no logo image, T-16) and `display-md` `Gia phả dòng họ`. Sub:
`body-lg` `Đăng nhập để xem gia phả dòng họ`. Then: Email field, Mật khẩu field with a
show/hide toggle (48dp, labelled `Hiện mật khẩu` / `Ẩn mật khẩu`), `Quên mật khẩu?` as a
ghost text button right-aligned, `Đăng nhập` primary `lg` full-width. Below a
`Hoặc` divider (a centred label on a background step, not a rule): `Tiếp tục với Google`,
`Tiếp tục với Apple` (iOS). Footer: `Chưa có tài khoản? Đăng ký`.

**Desktop.** Same column, max-width 440, centred in the viewport, with the page ground at
`surface` and the form on `surface-container-lowest` `radius-xl` `elev-1`. No marketing
split-screen — this is an invite-only family tool, not a SaaS signup.

**States.**
- *Loading* — button loading state; fields become read-only, not disabled (a disabled
  field loses its value announcement).
- *Wrong credentials* — banner above the form, `danger-container`, message from
  `error.message`. Fields keep their values. Password is **not** cleared.
- *403 `email_not_verified`* → route to 7.1c.
- *429 `rate_limited`* — the submit button becomes `Thử lại sau {n} giây` and counts
  down from `detail.retry_after`; the countdown is announced once, not every second.
- *503 `auth_provider_unavailable`* — `warning-container` banner:
  *"Hệ thống đăng nhập tạm thời gián đoạn. Đây không phải lỗi mật khẩu của bạn. Xin thử
  lại sau ít phút."* Explicitly not a credentials error.
- *Missing Supabase config (dev)* — existing copy retained.

**After success.** Never trust the login body's `has_pending_membership` or `clan_id`
(both are known-broken, per the integration guide). The client shows a **full-screen
brand hold** — wordmark + `Đang mở gia phả dòng họ…` — while it calls `GET /auth/me` and
`GET /me/clans`, then routes. This deliberate ~1s hold is preferable to painting a
dashboard with a possibly-wrong clan name (§9-J9).

#### 7.1b Đăng ký

**Purpose.** Join an existing dòng họ by code, or create a new one.

**Mobile.** Segmented control at the top: `Tham gia dòng họ` | `Tạo dòng họ mới`.
- *Tham gia*: Họ và tên · Email · Mật khẩu (with a plain-language strength hint, not a
  meter bar) · **Mã dòng họ** with helper *"Mã do quản trị dòng họ cung cấp, ví dụ:
  nguyen-huu-thanh-oai."*
- *Tạo mới*: Họ và tên · Email · Mật khẩu · Tên dòng họ · Mã dòng họ (auto-suggested,
  slugified live from the name, editable) with helper *"Người khác dùng mã này để xin
  tham gia dòng họ của bạn."*

**States.** Field-level validation errors for `auth.clan_id_required_for_join`,
`auth.clan_name_required_for_create`, `auth.clan_slug_taken` (inline on the slug field
with a suggested alternative), `clan_not_found` (inline on the code field:
*"Không tìm thấy dòng họ với mã này. Xin kiểm tra lại với quản trị dòng họ."*).

**Critical: registration is non-enumerating.** A `201` always routes to the same
"check your email" screen. The UI must never claim an account was created, and must
never say "email này đã được đăng ký".

> **Đã gửi thư tới hộp thư của bạn**
> Chúng tôi vừa gửi một thư tới **{email}**. Xin mở thư và bấm vào liên kết để tiếp
> tục. Nếu bạn đã có tài khoản với địa chỉ này, thư sẽ hướng dẫn bạn đặt lại mật khẩu.
> [Gửi lại thư] [Về trang đăng nhập]

`Gửi lại thư` has a 60s cooldown shown as `Gửi lại sau {n} giây`.

#### 7.1c Xác thực email

Two surfaces:

1. **Blocked-at-login** (`403 email_not_verified`): full screen, `heritage-container`
   icon block, `headline` `Xin xác thực email trước`, `body-lg` explanation, primary
   `Gửi lại thư xác thực`, ghost `Đổi địa chỉ email` → support/admin contact.
2. **Landing from the email link**: three states in one screen — *Đang xác thực…*
   (spinner + text, no skeleton, this is genuinely a wait), *Xác thực thành công* →
   `success-container`, auto-route to login after 3s with a manual `Đăng nhập ngay`, and
   *Liên kết đã hết hạn* → `warning-container` + `Gửi lại thư xác thực`.

**Open risk.** The landing URL parameter shape (`token_hash`+`type` vs PKCE `?code=`)
is unresolved in the contracts. The screen is designed to handle both and to show the
expired state on any failure rather than a raw error.

**Role.** N/A — pre-authentication.

---

### 7.2 Chờ duyệt · Chọn dòng họ · Dòng họ bị tạm ngưng

#### 7.2a Chờ duyệt (pending approval)

**Purpose.** Tell a person who has done everything right that they are waiting on a
human, and give them something to do.

This is not an error and must not look like one. `heritage-container` ground, generous
whitespace.

**Mobile / Desktop.** Same centred column (max-width 520 on desktop).
- `display-md` **Đang chờ quản trị dòng họ duyệt**
- `body-lg` *"Bạn đã gửi yêu cầu tham gia **dòng họ {clan_name}**. Quản trị dòng họ sẽ
  xem xét và duyệt trong thời gian sớm nhất. Chúng tôi sẽ gửi thông báo ngay khi bạn
  được duyệt."*
- A quiet three-step progress list (this **is** a real sequence, so numbering carries
  information): `1. Tạo tài khoản ✓` · `2. Gửi yêu cầu tham gia ✓` ·
  `3. Chờ quản trị duyệt ◦`
- Actions: `Kiểm tra lại` (refetches `GET /auth/me`), `Tham gia dòng họ khác`
  (`POST /auth/onboard`), `Đăng xuất` as ghost.

**States.** *Checking* — `Kiểm tra lại` in loading state. *Still pending* — toast
`Yêu cầu của bạn vẫn đang chờ duyệt.` *Approved on refetch* — success toast and
immediate route to the dashboard. *No membership at all* (`is_approved` false,
`has_pending_membership` false, `clan_id` null) → onboarding variant of this screen with
the join/create segmented control from 7.1b.

**Note.** A pending user *can* accept an invitation and can call `POST /auth/onboard`,
so those two paths stay live here; everything clan-scoped is absent, not disabled.

#### 7.2b Chọn dòng họ (clan picker)

**Purpose.** For members of more than one dòng họ, choose the active one. Reached on
first login with >1 clan, from `400 multiple_clans_no_selection`, and from the clan
switcher.

**Mobile.** Full screen, `display-md` `Chọn dòng họ`, `body-lg` *"Bạn là thành viên của
{n} dòng họ. Xin chọn dòng họ bạn muốn xem."* Then a stack of large tap targets (min
88dp): clan name in `title-lg` Jakarta, role chip (`Quản trị` / `Biên tập` /
`Người xem`), `body-md` `Tham gia từ {joined_at}`, chevron. Selected clan carries a
check and `primary-container` ground.

**Desktop.** Same list, max-width 560, centred; two columns at ≥1280 if >6 clans.

**States.** *Loading* — three shape-matched row skeletons. *Error* — `ErrorState` with
retry. *Empty* — cannot legitimately happen for an approved user; if `/me/clans` returns
`[]` the user is pending, so route to 7.2a rather than showing an empty picker.
*Selecting* — the tapped row shows an inline ring; the rest dim to 0.6; on success, full
cache reset then dashboard.

**Rule.** The picker is never skipped for multi-clan users, and the previously selected
clan is remembered per device.

#### 7.2c Dòng họ bị tạm ngưng (`clan_suspended`)

Full screen, `warning-container`. `headline` `Dòng họ {clan_name} đang tạm ngưng`,
`body-lg` explanation, `error.message` from the envelope, and — this is the important
part — `Chuyển sang dòng họ khác` when `/me/clans` has other entries, otherwise
`Đăng xuất`. Never a dead end (T-17).

---

### 7.3 Trang chủ / Dashboard

**Purpose.** In one screen: what is coming up in the family calendar, what changed, and
the three or four things this person actually does.

**Mobile.** Scrolling column:

1. **Greeting block** — `title-lg` `Chào {tên gọi}`, `body-md` `Dòng họ {clan_name} ·
   {role}`. No avatar-heavy header.
2. **Sắp tới** — the single most valuable card in the product. Up to 3 upcoming events
   from `GET /events/upcoming`, each a row: event-type icon, title `title-md`, solar
   date, lunar line when present, and a `còn {n} ngày` chip. Giỗ entries carry the
   `heritage` family. `Xem tất cả` ghost link.
3. **Quick actions** — 2×2 of large tonal tiles, filtered by role:
   `Cây gia phả` · `Thành viên` · `Thêm thành viên` (editor+) · `Ảnh & tài liệu`.
4. **Dòng họ trong số liệu** — three stat tiles: `Thành viên`, `Số đời`, `Sự kiện năm
   nay`. `tabular-nums`, `display-md` figure over `label-md` caption.
5. **Cần bạn xử lý** (admin only) — pending approvals count, identity claims count,
   and the thủy tổ prompt if the clan has no founder. `heritage-container` when it
   contains the founder prompt, `info-container` otherwise.

**Desktop.** Sidebar + 12-column content. Asymmetric by design: `Sắp tới` occupies a
7-column card on the left; `Cần bạn xử lý` + stats stack in a 5-column right rail;
quick actions become a single row of four wide tiles below. Not a uniform grid.

**States.** *Loading* — skeletons matching each card's real geometry; the greeting
renders immediately from cached profile. *Empty events* — `Chưa có sự kiện nào sắp
tới.` + `Thêm sự kiện` (editor+) or nothing (viewer). *Empty clan (0 persons)* — the
whole page collapses to a single onboarding card: `Bắt đầu dựng gia phả` →
`Thêm người đầu tiên` (admin/editor) / `Dòng họ chưa có dữ liệu. Xin chờ quản trị dòng
họ bắt đầu.` (viewer). *Partial failure* — each card fails independently with its own
inline retry; one dead endpoint never blanks the dashboard. *Offline* — OfflineBar +
cached content with a `Cập nhật lúc {giờ}` line.

**Role.** Viewer sees 1, 2, 4 and a two-tile quick-action row. Editor adds
`Thêm thành viên`. Admin adds card 5 and the admin nav item.

---

### 7.4 Cây gia phả

The hardest screen, and the one where web and mobile diverge most.

**Purpose.** Let someone see where a person sits in the lineage — đời, cha/mẹ, các bà
vợ, con cháu — and move along it without getting lost.

#### 7.4a The tree itself

**Desktop.** Pan/zoom canvas.
- Nodes are `PersonNodeCard`s laid top-down by đời. Left rail shows a **đời ruler**:
  sticky labels `Đời 1 · Đời 2 · …` aligned to each row band; bands alternate between
  `surface` and `surface-container-low` — that background step is the only separator
  (no-line rule).
- Connectors are 2px `secondary` @ 40% curves. These are data relations, not section
  rules, so they are exempt from the no-line rule.
- Floating glass toolbar, bottom-centre: `−` `100%` `+` · `Vừa khung` · `Chế độ danh
  sách` · `Xuất PDF`. Exactly one glass surface on this screen.
- Right side panel (≥1280) shows the selected person's summary and
  `Xem hồ sơ đầy đủ →`.
- Depth control: `Hiển thị {n} đời` slider, 1–10, default 5 (not the API's 10 — ten đời
  of a real clan is thousands of nodes over 3G).
- Keyboard: arrow keys move between siblings/parent/children, `Enter` opens the sheet,
  `+`/`−` zoom, `Home` returns to thủy tổ. Focus ring on the focused node at all times.

**Mobile.** **Not a pan/zoom canvas.** A pinch-zoom graph on a 5-inch screen at 200% text
scale is unusable, and it is exactly the older user who most needs this screen. Mobile
uses a **focus navigator** built on `GET /tree/focus/{id}`:

- Top: breadcrumb of ancestors as a horizontally scrollable chip row
  `Thủy tổ › Đời 2 Nguyễn Hữu Đàm › Đời 3 …`, tappable to re-root.
- Middle: the focused person as a large `PersonNodeCard` (full width), with `Cha`/`Mẹ`
  compact rows above it.
- Below: `Con cái` grouped by wife per §3.3, each child a tappable row that re-roots the
  view (`dur-3` slide).
- `has_more_descendants` on a boundary node renders `Còn {…} đời nữa →`.
- Bottom glass bar: `Về thủy tổ` · `Tìm quan hệ` · `Chế độ cây` (a read-only, zoomable
  overview for users who want it, explicitly secondary).

**đa thê rendering** (both clients). Under a father with two wives:

```
Đời 4 · Nguyễn Hữu Đàm  [Thủy tổ chip if applicable]
├─ Vợ cả · Trần Thị Mão        ← WifeGroupHeader, surface-container-low band
│   ├─ Nguyễn Hữu Lộc   Đời 5
│   └─ Nguyễn Thị Sen    Đời 5
├─ Vợ hai · Lê Thị Nhàn        ← second band, same weight, same node size
│   └─ Nguyễn Hữu Trác  Đời 5
└─ Chưa rõ mẹ                   ← only when mother_id is null
    └─ Nguyễn Hữu Bảo   Đời ?
```

**Null đời rendering.** Any node whose `generation` is null shows `Đời ?` (§3.2). On
desktop, nodes with null đời cannot be placed on the đời ruler, so they render in a
**separate tray** below the canvas headed `Chưa nối vào thủy tổ ({n})` — placing them
in a đời band would be a guess, and dropping them would hide real people (§9-J3).

**Pedigree-collapse stubs.** Per §3.4.

#### 7.4b Chưa có thủy tổ — `404 clan_founder_not_found`

**This is an onboarding state, not an error.** No error iconography, no red, no "không
tìm thấy".

Centred card on the tree canvas, `heritage-container`, `radius-xl`:

> **Dòng họ chưa có thủy tổ**
> Cây gia phả được dựng từ thủy tổ — người khởi đầu dòng họ. Xin chọn một người trong
> danh sách thành viên làm thủy tổ để bắt đầu dựng cây. Bạn có thể đổi lại sau.
>
> *(admin)* [Chọn thủy tổ] [Thêm người đầu tiên]
> *(editor / viewer)* Quản trị dòng họ cần chọn thủy tổ trước khi cây gia phả hiển
> thị được. [Xem danh sách quản trị]

`Chọn thủy tổ` opens a searchable person picker (sheet on mobile, dialog on web) →
`PUT /clans/me/founder`. Confirmation is required and names the person:
*"Đặt **{tên}** làm thủy tổ của dòng họ {clan_name}?"*

**The same state reappears** if the current founder is soft-deleted. The copy then adds:
*"Thủy tổ trước đây đã bị xóa khỏi gia phả."* with two admin actions —
`Khôi phục {tên}` (`POST /persons/{id}/restore`) and `Chọn thủy tổ khác`. Two paths,
because the backend genuinely has two recovery paths.

#### 7.4c Other states

*Loading* — node-shaped skeletons in a plausible đời layout, đời ruler already drawn
(no shift). *Large tree* — beyond ~300 rendered nodes, show a banner
*"Cây gia phả rất lớn. Đang hiển thị {n} đời."* with a depth control, rather than
attempting to draw everything. *Error* — `ErrorState` with retry and a
`Chế độ danh sách` fallback. *Offline* — last successfully loaded tree, OfflineBar,
navigation limited to cached nodes.

**Role.** Viewer: no long-press edit actions, no `Chọn thủy tổ`, `Xuất PDF` allowed
(RBAC permits it for all roles).

---

### 7.5 Danh sách thành viên

**Purpose.** Find a person by name in a clan of several hundred, and see enough to know
it is the right one.

**Mobile.** Sticky glass header: SearchField + a `Bộ lọc` chip showing the active count.
Body: `CursorList` of `PersonRow` (avatar 40, name `title-md`, second line
`{năm sinh} – {năm mất}` or `Sinh {…}`, trailing đời badge). Filter sheet:
`Đời` (multi-select chips incl. `Chưa xác định`), `Giới tính`, `Còn sống / Đã mất`,
`Chi/nhánh`. FAB `+ Thêm thành viên` (editor+).

**Desktop (≥1024).** This data **is** tabular, so a table is allowed here: columns
`Họ và tên` · `Đời` · `Năm sinh` · `Năm mất` · `Chi/nhánh` · `Cập nhật`. Row separation
is by `space-2` gap and a `surface-container-low` row ground, not by rules; in
high-contrast mode `outline-variant` @15% row separators are permitted (the mandate's
own exception). Sticky header row. Left rail carries the filters as a persistent panel
rather than a sheet.

**Pagination — cursor only.** There is no page number anywhere in the UI, because the
API has no concept of one.
- Mobile: auto-loads the next page when the sentinel is 400px from the viewport, **and**
  always renders a real `Tải thêm` button at the end — on 3G the auto-load frequently
  fails and the user needs something to press.
- Web: an explicit `Tải thêm` button only. Infinite scroll on desktop breaks keyboard
  users and hides the page footer.
- `has_more: false` → an end marker `Đã hiển thị hết {n} thành viên.`
- `400 invalid_cursor` → silently drop the cursor, refetch page 1, preserve scroll
  position, no visible error. The user did nothing wrong.

**States.**
- *First load* — 8 shape-matched row skeletons.
- *Loading next page* — 2 skeleton rows appended below existing content; existing rows
  never move.
- *Searching* — existing results stay visible at 0.6 opacity with a ring in the search
  field. Result count announced politely: `{n} kết quả`.
- *Empty (no members)* — `Dòng họ chưa có thành viên nào` + `Thêm thành viên đầu tiên`
  (editor+) / an explanation (viewer).
- *Empty (no search results)* — `Không tìm thấy "{query}"` + `Xóa bộ lọc` and, for
  editor+, `Thêm "{query}" làm thành viên mới`.
- *Error* — `ErrorState`; already-loaded pages remain visible above it.
- *Offline* — cached first page + OfflineBar; `Tải thêm` disabled with the reason stated
  in text.

**Role.** Viewer: no FAB, no row-level `⋯` actions. Admin: row `⋯` gains `Xóa` and
`Đặt làm thủy tổ`.

---

### 7.6 Hồ sơ một người

**Purpose.** Everything known about one person, honestly — including how much is
uncertain.

**Mobile.** Scrolling column:

1. **Header** — avatar 96 centred, name `headline` Jakarta, đời badge + role/status
   chips (`Thủy tổ`, `Đã mất`, `Con nuôi` where applicable), and the life line:
   `1892 – khoảng 1961` with precision chips. Actions per role (§3.5).
2. **Tên gọi** — only the name fields that exist: `Tên húy`, `Tên tự`, `Tên thụy`,
   `Biệt hiệu`, `Chức tước`. Each is a label/value pair; absent fields are omitted, not
   shown as empty. Vietnamese name types carry a small info affordance explaining what
   each means — most users have never had to distinguish tên tự from tên thụy.
3. **Ngày tháng** — birth and death, each rendered by `HistoricalDateDisplay` with its
   precision chip and lunar line. **This is where all four precisions must coexist
   gracefully** and it is the profile's design test:
   - `Ngày sinh · 15/08/1948` (exact)
   - `Ngày mất · khoảng 1961` `[khoảng]` / `Âm lịch · 20/11 Tân Sửu`
   - `Ngày sinh · 1892` `[năm]`
   - `Ngày mất · Không rõ` `[không rõ]`
4. **Nơi chốn** — nơi sinh, nơi mất, nơi cư trú.
5. **Quan hệ** — `Cha mẹ`, `Vợ/chồng` (with `Vợ cả`/`Vợ hai` order chips and marriage
   status), `Con cái` **grouped by mother per §3.3**, `Anh chị em`. Each row navigates.
6. **Ảnh & tài liệu** — horizontal thumbnail strip; each item shows type icon + title,
   so it reads correctly before (or without) the image. Presigned URLs expire in one
   hour: on a 403 the client refetches `GET /documents/{id}` once, and the thumbnail
   shows a `Tải lại` affordance rather than a broken image.
7. **Tiểu sử** — `body-lg`, max ~65 characters per line, `Xem thêm` past 6 lines.
8. **Ghi chú** and, for admin, an audit line `Cập nhật lần cuối {…} bởi {…}`.

**Desktop (≥1280).** Two columns: main 1fr (dates, places, biography, documents) and a
360px aside (header card, relationships, quick actions). Below 1280 it collapses to the
mobile order.

**States.** *Loading* — full shape-matched skeleton including the avatar circle.
*Not found / cross-clan* — 404 renders `Không tìm thấy người này trong dòng họ
{clan_name}.` with `Về danh sách thành viên` — never leaks that the person may exist in
another clan. *Soft-deleted (admin view)* — a `warning-container` banner
*"Người này đã được xóa khỏi gia phả ngày {…}."* + `Khôi phục`; all content read-only.
*Sparse record* — a person with nothing but a name is valid and must look intentional:
sections 2–8 collapse and one line reads *"Gia phả hiện chỉ ghi tên. Bạn có thể bổ sung
thông tin."* (editor+).

**Role.** Per §3.5. Viewer sees the permanent role line and no buttons.

---

### 7.7 Thêm / Sửa người

**Purpose.** Let an editor record what the gia phả actually says — including what it
says vaguely — without fighting the form.

**Mobile.** Full-screen form, sectioned, with a sticky bottom action bar (`Hủy` ghost /
`Lưu` primary) that sits above the keyboard.

**Desktop.** Dialog at ≥1024 (max-width 720) for create; full page for edit, with the
same sticky footer.

**Sections.** `Tên gọi` (Họ và tên required; the four Vietnamese name types in a
collapsed `Tên gọi khác` group) · `Giới tính` (segmented: Nam / Nữ / Không rõ) ·
`Ngày sinh` (HistoricalDateField) · `Ngày mất` (HistoricalDateField, revealed by an
`Đã mất` switch) · `Nơi chốn` · `Chi/nhánh` · `Tiểu sử` · `Ghi chú`.

**Copy that matters.** The precision control's helper text is the whole point of the
product:

> Gia phả cũ thường không ghi ngày chính xác. Hãy chọn đúng mức chắc chắn mà gia phả
> ghi — "khoảng 1750" là một câu trả lời đúng, không phải câu trả lời thiếu.

#### 7.7a Validation and warnings

- Client-side: required `Họ và tên`; year plausibility (1000–current+1); death not
  before birth when both are exact.
- `422 relationship.parent_too_young` → inline error on the relationship field with
  `detail.min_age_gap` and `detail.actual` spelled out in Vietnamese.
- `meta.warning` on a successful write (unusual age gap, low gap on estimated dates) →
  the save **succeeds**, and a `warning` toast appears afterwards:
  *"Đã lưu. Lưu ý: chênh lệch tuổi giữa cha/mẹ và con là {n} năm — xin kiểm tra lại nếu
  đây là nhầm lẫn."* A warning never blocks a save.
- Unsaved-changes guard on back/close: *"Bạn có thay đổi chưa lưu. Thoát và bỏ thay
  đổi?"*

#### 7.7b Save states

*Idle* → *Submitting* (button loading, fields read-only) → *Success* (toast
`Đã lưu thay đổi.` + return) or an error state. On network failure the form retains
everything and offers `Thử lại` — the user's typing is never lost.

#### 7.7c `409 stale_write` — "người khác vừa sửa"

The most important error dialog in the product. Two people editing the same ancestor is
normal in an active clan.

Dialog, `radius-xl`, max-width 560, **not** dismissible by scrim tap:

> **Người khác vừa sửa hồ sơ này**
> Trong lúc bạn đang nhập, một người khác đã cập nhật hồ sơ **{tên}**. Xin chọn giữ lại
> nội dung nào cho từng mục.

Body: a **field-level comparison list showing only the fields that actually differ** —
not a full-record diff. Each row:

```
Ngày mất
  Bản của bạn      khoảng 1961      [Giữ bản của tôi]  ← default when the user edited this field
  Bản mới nhất     15/11/1961       [Dùng bản mới]     ← default when the user did not
```

Selection is a two-option segmented control per field, so both choices are always
visible and neither is hidden behind a colour.

Actions: `Lưu bản đã chọn` (primary) · `Bỏ thay đổi của tôi, tải lại` (ghost) ·
`Sao chép nội dung của tôi` (ghost — the escape hatch when the user just wants their
text back).

Behaviour: on open, refetch the record for current values and `version`; on save,
resubmit with the fresh `expected_version`. **Never auto-resubmit** and never retry with
the stale version. If the resubmit 409s again, reopen the dialog with the newer data and
add *"Hồ sơ này đang được nhiều người sửa cùng lúc."*

Mobile presents the same content as a full-screen sheet, one field per card. See §9-J6
for why this is field-level rather than a three-way merge.

**Role.** Editor and admin only. A viewer never reaches this screen; if a role is
downgraded mid-edit, the save returns 403 and the dialog explains it plainly with a
`Sao chép nội dung của tôi` escape.

---

### 7.8 Sự kiện / Giỗ chạp

**Purpose.** The clan's calendar of giỗ, sinh nhật, kỷ niệm and việc họ — the screen that
gets opened most often by the people who use the product least.

**Mobile.** Tabs: `Sắp tới` | `Cả năm`.
- *Sắp tới* — chronological cards from `GET /events/upcoming`. Each: event-type icon in
  a tonal circle (giỗ uses `heritage-container`), title `title-md`, person link,
  solar date `dd/MM/yyyy`, lunar line when applicable, `còn {n} ngày` chip (`Hôm nay` /
  `Ngày mai` for 0/1), and `Hằng năm` chip when recurring.
- *Cả năm* — a month-grouped list, not a calendar grid. A 7-column month grid at 200%
  text scale on a 320dp screen cannot show a Vietnamese event title; the list can.
  Sticky month headers `Tháng 8, 2026`.
- FAB `+ Thêm sự kiện` (editor+).

**Desktop.** Two columns: a month calendar grid on the left (≥1024, where the grid does
fit) and the upcoming list on the right. Days with events carry a filled dot per event
type; selecting a day filters the right column. The list is authoritative; the grid is
navigation.

**Two different lunar concepts, never conflated** (§9-J7):

| | Source | Label in UI |
|---|---|---|
| `HistoricalDate.lunar` | User-entered text, verbatim, never computed | `Âm lịch (ghi trong gia phả)` |
| Next lunar occurrence | Backend-computed (ADR-018, Hồ Ngọc Đức, UTC+7) | `Giỗ năm nay · {dd/MM/yyyy} dương lịch` |

An event card for a giỗ therefore reads:

```
Giỗ cụ Nguyễn Hữu Đàm            [Hằng năm] [Giỗ]
Âm lịch · 20/11
Giỗ năm nay · 29/12/2026 (dương lịch)      còn 12 ngày
```

**Event form** (editor+): Loại sự kiện (Ngày giỗ / Sinh nhật / Kỷ niệm ngày cưới /
Lễ việc họ / Tùy chỉnh) · Tiêu đề · Người liên quan (person picker) · Ngày (a
HistoricalDateField) · `Tính theo âm lịch` switch · `Lặp lại hằng năm` switch ·
`Nhắc trước {n} ngày` · Mô tả.

**The precision trap, designed for.** A recurring event whose `event_date_precision` is
not `exact` is stored and listed but **never notified and never surfaced in
`/events/upcoming`**. Silence would be a broken promise, so the form warns at input
time, inline under the recurrence switch, as `warning-container`:

> Ngày này được ghi là **{khoảng 1950}**. Vì chưa có ngày chính xác, hệ thống sẽ **không
> gửi nhắc hằng năm** cho sự kiện này. Sự kiện vẫn được lưu và hiển thị trong danh sách.

The same notice appears as a chip `Không nhắc tự động` on the event card in the list,
so a user who set it months ago is not left wondering.

**States.** *Loading* — 4 card skeletons. *Empty upcoming* — `Không có sự kiện nào trong
{n} ngày tới.` + `Thêm sự kiện` (editor+). *Empty year* — `Dòng họ chưa ghi sự kiện
nào.` with an explanation of what giỗ tracking does. *Error* — `ErrorState`. *Offline* —
cached upcoming list + OfflineBar; `còn {n} ngày` recomputed from the device clock and
labelled `Tính theo giờ máy`.

**Role.** Viewer: no FAB, no per-card `⋯`. Editor and admin may create, edit and delete
events (RBAC allows editors to delete events).

---

## 8. Where web and mobile deliberately diverge

Divergence is a cost; each of these buys something specific.

| # | Divergence | Why |
|---|---|---|
| D1 | **Tree: canvas (web) vs focus navigator (mobile)** | A pan/zoom graph is the right tool at 1440px and the wrong one at 320dp with 200% text. Mobile is built on `GET /tree/focus/{id}` and navigates person-by-person; web renders `GET /tree`. Both render đời, đa thê grouping and stubs identically. |
| D2 | **Sự kiện: calendar grid (web) vs month list (mobile)** | A 7-column grid cannot hold a Vietnamese event title at large text sizes. Mobile groups by month in a list; web shows the grid *and* the list, grid as navigation only. |
| D3 | **Member list: table (web ≥1024) vs rows (mobile)** | The data is genuinely tabular and the desktop viewport supports it. This is the one place a rigid grid is permitted by the mandate. |
| D4 | **Pagination: auto-load + button (mobile) vs button only (web)** | Infinite scroll on desktop breaks keyboard users and hides the footer; on mobile auto-load is expected, but the explicit button stays because it fails often on 3G. |
| D5 | **Hover states exist only on web** | Mobile substitutes pressed states and long-press sheets. No information is ever hover-only on either client (T-10). |
| D6 | **Tooltips: web only** | Mobile uses an info IconButton opening a sheet. |
| D7 | **Date entry: numeric fields (both) + native picker (mobile, exact only)** | The native wheel picker is faster for a 1990 birthday and useless for 1750. Offered only for `exact` precision within the last ~120 years. |
| D8 | **Documents: drag-and-drop (web) vs camera capture (mobile)** | Platform-native capability, same upload contract. |
| D9 | **Overlays: dialog/side panel (web) vs bottom sheet (mobile)** | Same content, same component contract, different presentation. |
| D10 | **Glass surfaces: up to two (web) vs one (mobile)** | Per-frame blur on a five-year-old Android is a real frame-budget cost; mobile spends it only on the bottom nav. |

Everything else — tokens, copy, states, validation, error mapping, đời/đa thê/precision
rendering — is identical by construction. If a behaviour differs and is not in this
table, it is a bug.

---

## 9. Judgement calls and open questions

Where the domain and good UI genuinely pulled in different directions.

**J1 — Three primaries in the codebase, and mobile disagrees with itself.**
`web/src/app/globals.css` declares primary `#c41e3a` (lacquer red, also bound to
`--ring`). Mobile declares a green primary **twice, at two different values**:
`mobile/lib/app/theme/colors.dart` says `#4A6741` and
`mobile/lib/core/theme/app_colors.dart` says `#37563B` — and it is the second one that
screens actually render, because `AppColors.primary` is what the widgets import. So
there is no single "mobile green" to reconcile with web; there are two, and the
`ColorScheme` one is dead code. The mobile rebuild (ADR-034) deletes both files, which
is precisely why this document has to state the replacement rather than inherit one.
All three values are defensible and all three are shipped. Rather than pick a winner,
this system **assigns them different jobs**: leaf green is `primary` (interaction —
buttons, links, active nav, selection), and lacquer + gilt become the reserved
`heritage` family (thủy tổ, giỗ, đời badges, ancestral emphasis). This keeps the
"arbor" reading of the design system, keeps Vietnamese ceremonial colour where it means
something, and — practically — stops red from being spent on ordinary buttons so that it
still reads as significant when it marks the thủy tổ. The shipped values shift slightly
for contrast (`#3E5C38`, `#A3182F`); `gilt-decor` keeps `#D4AF37` exactly.

**J2 — No-1px-border vs. accessibility.** The no-line rule and WCAG focus visibility are
in direct conflict. Resolution: **focus rings, error indicators, active tab indicators,
and relationship connectors are not "lines" in the mandate's sense** — they are state
and data, not section separation — and are exempt. Section separation remains
background-step only. The mandate's own high-contrast exception (`outline_variant` at
15%) is additionally extended to table row separation in the desktop member list, where
scanning a wide row without any separator is measurably worse.

**J3 — `generation: null` on a spatial layout.** đời is the tree's vertical axis, so a
node with no đời has no honest position. Guessing (place it under its parent's band) is
forbidden by the domain rules. Dropping it hides a real person. Resolution: on desktop,
null-đời nodes render in a labelled tray below the canvas (`Chưa nối vào thủy tổ`); on
mobile they appear in their parent's child list with a `Đời ?` badge, because the focus
navigator has no đời axis to violate. Both are honest; neither hides anyone.

**J4 — Stubs that claim descendants.** `pedigree_collapse_ref` nodes have empty
`children` but may report `has_more_descendants: true`. An expander that opens to
nothing is worse than no expander, so stubs get **no expand control at all** — only
`Xem ở nhánh chính →`. We deliberately ignore `has_more_descendants` on stubs.

**J5 — Viewers and the missing change-request feature.** "Don't show viewers disabled
buttons" is easy; "give viewers a way to contribute" is not, because no
change-request/suggestion endpoint exists (it is on the DB roadmap, not built). The
honest design is: remove all write affordances, state the role once in plain language,
and link to the admin list. We deliberately do **not** ship a "Đề nghị sửa" button that
would go nowhere. **Open question for the backend:** a suggestion/change-request surface
is the correct long-term answer and would change this screen.

**J6 — `stale_write` conflict resolution depth.** The contract asks the client to
re-apply the user's edit onto fresh data. A full three-way merge UI is beyond a
78-year-old on a phone; blind last-write-wins loses another editor's work. Resolution:
**field-level choice, limited to fields that actually differ**, with the default per
field set by whether *this* user touched it. Typically one or two rows, occasionally
none (in which case we resubmit silently with the fresh version, since there is nothing
to resolve). A `Sao chép nội dung của tôi` escape exists for anyone who wants out.

**J7 — Two kinds of lunar date on one screen.** `HistoricalDate.lunar` is verbatim
user-entered text the server never computes, while ADR-018 *does* compute the next lunar
occurrence for recurring events. Showing both as "âm lịch" would make the product look
like it is contradicting itself. They are labelled differently everywhere
(`Âm lịch (ghi trong gia phả)` vs `Giỗ năm nay · … (dương lịch)`), and the UI never
reformats, validates, or converts the stored lunar string.

**J8 — Estimated dates are normal, not warnings.** The strong instinct is to flag
`circa`/`unknown` with warning colour. In a gia phả covering 1750, the *exact* date is
the exception. Precision chips are therefore neutral-toned and purely informational.
Warning colour is reserved for cases where imprecision has a real consequence — the
recurring-event notice in §7.8.

**J9 — The post-login hold.** The login response's `clan_id` is undefined for multi-clan
users and its `has_pending_membership` is always false. Painting the dashboard from it
risks showing one family's name over another family's data. We accept a ~1 second branded
hold while `GET /auth/me` and `GET /me/clans` resolve. In a genealogy product, being
briefly slow beats being briefly wrong.

**J10 — Locale must not come from the profile.** `preferred_locale` always returns `"vi"`
regardless of what was saved. The language switcher reads and writes client storage (and
`PATCH /auth/me` for persistence) and never reflects the profile response, or a user who
picked English would see it silently revert on every login.

**J11 — Avatars must not depend on `avatar_url`.** `persons.avatar_url` is an
undefined client-writable string that will silently expire if a presigned URL is written
into it, and presigned URLs live one hour. Initials avatars are therefore the primary
rendering and photographs are a progressive enhancement layered on top. **Open question
for the backend:** what belongs in `avatar_url` is still undecided.

**J12 — Uppercase and Vietnamese.** The editorial instinct toward tracked-out uppercase
eyebrow labels actively damages Vietnamese legibility at small sizes. Caps is restricted
to short, mark-free words; everywhere else the eyebrow keeps its tracking and drops the
caps.

### Deferred (not designed here)

Admin panel (approvals, roles, invitations), identity claims, documents library,
notification settings, platform/super-admin surfaces, export/PDF layout, onboarding
tour, and the change-request feature from J5.

---

## Related documents

- `mobile/CLAUDE.md` — Arbor Heritage mandates (binding)
- `docs/architecture/tree-read-model.md` — đời, đa thê, pedigree collapse, thủy tổ
- `docs/architecture/domain-rules.md` — invariants, Vietnamese glossary
- `docs/architecture/rbac.md` — role matrix
- `docs/contracts/README.md` — envelope, `HistoricalDate`
- `docs/contracts/frontend-integration-guide.md` — client states and error handling
- `docs/contracts/error-codes.md` — full error catalogue
