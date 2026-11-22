/**
 * The clan as its own admins see it: the `clans` row (`GET /clans/me`), its member counts
 * (`?include=stats`), and the two account lists (`GET /clans/me/users` and `/users/pending`).
 *
 * `ClanProfile` is named for what it is, the clan's profile row. It used to be `ClanSettings` in
 * the legacy `lib/types/admin.ts`, a name that pointed at the `clan_settings` table ADR-054
 * dropped; no endpoint ever read or wrote that table (docs/contracts/rest-clans-api.md,
 * "Versioning & Compatibility Rules").
 *
 * Plain types only: no React, no fetch, no zod (`domain-is-pure`).
 */

import type { ClanRole } from '../capability/capability'

export interface ClanProfile {
  id: string
  name: string
  /** The clan code. Identity, never editable through `PATCH /clans/me`. */
  slug: string
  description: string | null
  originPlace: string | null
  /** A plain year, not a HistoricalDate (docs/contracts/rest-clans-api.md). */
  foundedYear: number | null
  avatarUrl: string | null
  motto: string | null
  ancestralHallLocation: string | null
  clanRules: string | null
  isActive: boolean
  createdAt: string
  updatedAt: string
}

/** The eight fields `PATCH /clans/me` accepts. An omitted field is left alone. */
export interface ClanProfileUpdate {
  name?: string
  description?: string | null
  originPlace?: string | null
  foundedYear?: number | null
  avatarUrl?: string | null
  motto?: string | null
  ancestralHallLocation?: string | null
  clanRules?: string | null
}

/** `GET /clans/me?include=stats`: exact counts the backend computes, not a page size. */
export interface ClanStats {
  /** Every account membership row of the clan, approved or not. */
  totalUsers: number
  approvedUsers: number
  /** Accounts waiting for an admin's approval. */
  pendingUsers: number
  /** Persons in the clan's tree (`clan_memberships`), not accounts. */
  totalMembers: number
}

/** One approved account (`ClanUserSummary`). No email: this list is readable by every viewer (ADR-039). */
export interface ClanUser {
  id: string
  userId: string
  /**
   * The wire types `role` as a bare string. `null` when it is none of the three clan roles, so a
   * screen says nothing about a role it cannot name rather than print a raw wire value.
   */
  role: ClanRole | null
  personId: string | null
  displayName: string | null
  createdAt: string
}

/** One pending join request (`PendingClanUserSummary`). `email` is on this admin-only row only. */
export interface PendingClanUser extends ClanUser {
  email: string | null
}

export interface ClanUsers {
  approved: ClanUser[]
  pending: PendingClanUser[]
}
