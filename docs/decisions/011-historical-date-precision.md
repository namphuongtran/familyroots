# ADR-011: HistoricalDate — Precision Model Replaces `*_approx`

## Status
Accepted (2026-07-11 contract freeze — shipped, migrations 012→014)

## Context
Multi-century gia phả data has dates known only as "khoảng 1750", a year, a month,
or not at all — plus lunar-calendar renditions. A boolean `*_approx` flag couldn't
express degrees of uncertainty, and clients had no honest way to render fuzzy dates.
This was the #1 retrofit-painful contract, so it was frozen before frontend work.

## Decision
- Storage: each genealogical date gains `*_precision` (`exact|year|month|circa|unknown`,
  NOT NULL, default `'exact'`) and `*_display` (VARCHAR(100), the human text shown when
  not exact). Applies to persons birth/death, events event_date, marriages
  marriage/divorce. The `*_approx` booleans were backfilled
  (approx→`circa`, date→`exact`, null→`unknown`) and **dropped**.
- API: every date field serializes as the object
  `{"date": ISO|null, "precision", "display", "lunar"}` (`app/schemas/historical_date.py`).
  Clients render `date` when precision is `exact`, else `display`.
- Write DTOs accept scalar `*_date` + optional `*_precision`/`*_display`.
- Lunar stays a **display-only string** (no structured lunar, no date ranges in v1).
- Domain rule: kinship age-based terms are only derived when **both** birth dates
  are `exact`.
- Out of scope (revisit if needed): earliest/latest ranges, structured lunar
  (can-chi + leap months), reign-era precision.

## Consequences
Easier: honest rendering of uncertain dates; sorting/anniversaries still use the
scalar `date`; precision can tighten over time without schema change.
Harder: breaking response reshape (accepted pre-frontend); one more concept for
clients; scalar-date exceptions must stay documented (document `taken_date`, tree
`SpouseNode` marriage dates, `/events/upcoming` `next_occurrence`).

Spec: `docs/contracts/README.md#historicaldate-canonical-date-shape`.
