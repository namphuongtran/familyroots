/**
 * The one place `relationships` query keys are built. A read and its
 * invalidation must not drift apart, so every hook imports its key from here.
 *
 * Every key is scoped by `clanId` first, matching the shape persons already
 * proved: a TanStack Query key is compared by value, so a key built from the
 * active clan refetches the moment `writeClanCookie` changes it — no manual
 * invalidation step for a clan switch, only for a mutation inside the same
 * clan.
 *
 * The two person-centric reads (`personMarriages`, `personParentChild`) are
 * keyed by the person id, because they live under `/persons/{person_id}/`
 * and the aside's single consumer cares about one person at a time. The
 * single-id reads (`marriageDetail`, `parentChildDetail`) are the editor's
 * data source — kept here because the editor sits in the same slice, even
 * though it is out of scope for this issue.
 */

type ClanId = string | null

const ROOT = 'relationships' as const

export const relationshipsKeys = {
  all: (clanId: ClanId) => [ROOT, clanId] as const,

  personMarriages: (clanId: ClanId, personId: string) =>
    [...relationshipsKeys.all(clanId), 'person-marriages', personId] as const,

  personParentChild: (clanId: ClanId, personId: string) =>
    [...relationshipsKeys.all(clanId), 'person-parent-child', personId] as const,

  marriageDetails: (clanId: ClanId) =>
    [...relationshipsKeys.all(clanId), 'marriage-detail'] as const,
  marriageDetail: (clanId: ClanId, id: string) =>
    [...relationshipsKeys.marriageDetails(clanId), id] as const,

  parentChildDetails: (clanId: ClanId) =>
    [...relationshipsKeys.all(clanId), 'parent-child-detail'] as const,
  parentChildDetail: (clanId: ClanId, id: string) =>
    [...relationshipsKeys.parentChildDetails(clanId), id] as const,
}
