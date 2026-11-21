'use client'

import { useQuery } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import { useMemo } from 'react'
import type { Person } from '@/domain/person/person'
import type { Marriage, ParentChild } from '@/domain/relationship/relationship'
import { useClientRequestContext } from '@/shared/http/context.client'
import { batchGetPersons, personsKeys } from '@/features/persons'
import { usePersonMarriages, usePersonParentChild } from '../hooks/use-relationship-queries'
import { spouseLabelOf } from './kinship-term'
import { RelationshipRow } from './RelationshipRow'
import { sortMarriagesBySpouseOrder, splitParentChildByOrientation } from './relationship-sort'

interface RelationshipsAsideProps {
  readonly personId: string
}

/**
 * Spec §7.6 "Hồ sơ một người" §5 "Quan hệ", in the desktop ≥1280 aside, and
 * the same content collapses inline below 1280 — layout is chosen by the
 * parent, not here, so this component only owns one column's width.
 *
 * Reads the person's marriages and parent-child edges through
 * `usePersonMarriages` / `usePersonParentChild`, batch-looks-up the other end
 * of each edge via `batchGetPersons` (persons slice, imported through its
 * public surface per `cross-feature-only-via-index`), and renders a
 * RelationshipRow per edge — marriages ordered by `spouse_order` per §3.3,
 * parent-child split into parents and children groups. Picks its own
 * `RequestContext` via `useClientRequestContext` rather than taking one as a
 * prop, same as `PersonsList`, so a Server-Component page can drop this
 * component in with just a `personId`.
 */
export function RelationshipsAside({ personId }: RelationshipsAsideProps) {
  const t = useTranslations('relationship')
  const { context, ready, refreshAuth } = useClientRequestContext()

  const marriages = usePersonMarriages(personId, { context, refreshAuth, enabled: ready })
  const parentChild = usePersonParentChild(personId, { context, refreshAuth, enabled: ready })

  const otherIds = useMemo(
    () => collectOtherIds(personId, marriages.data ?? [], parentChild.data ?? []),
    [personId, marriages.data, parentChild.data],
  )

  // One batch lookup for every other-person we need, deduplicated. Keyed by
  // clanId + sorted ids so a re-render over the same set reuses the cache
  // and so a mutation that invalidates `personsKeys.all(clanId)` invalidates
  // this too.
  const relatedPeople = useQuery({
    queryKey: [...personsKeys.all(context.clanId), 'batch', [...otherIds].sort().join(',')],
    queryFn: ({ signal }) =>
      batchGetPersons({ ids: otherIds, profile: 'summary' }, { context, refreshAuth, signal }),
    enabled: ready && otherIds.length > 0,
  })

  const personById = useMemo(() => indexById(relatedPeople.data?.items ?? []), [relatedPeople.data])

  const sortedMarriages = useMemo(
    () => sortMarriagesBySpouseOrder(marriages.data ?? []),
    [marriages.data],
  )
  const { parents, children } = useMemo(
    () => splitParentChildByOrientation(parentChild.data ?? [], personId),
    [parentChild.data, personId],
  )

  if (marriages.isError || parentChild.isError) {
    return (
      <aside aria-labelledby="relationships-aside-heading" className="space-y-3">
        <h2 id="relationships-aside-heading" className="text-foreground text-sm font-semibold">
          {t('aside_title')}
        </h2>
        <p className="text-destructive text-sm">{t('aside_error')}</p>
      </aside>
    )
  }

  const isLoading = !ready || marriages.isLoading || parentChild.isLoading

  return (
    <aside aria-labelledby="relationships-aside-heading" className="space-y-4">
      <h2 id="relationships-aside-heading" className="text-foreground text-sm font-semibold">
        {t('aside_title')}
      </h2>

      {isLoading ? (
        <p className="text-muted-foreground text-sm">{t('aside_loading')}</p>
      ) : (
        <>
          <section className="space-y-2" aria-labelledby="relationships-aside-spouses">
            <h3
              id="relationships-aside-spouses"
              className="text-muted-foreground text-xs font-medium uppercase"
            >
              {t('aside_spouses')}
            </h3>
            {sortedMarriages.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('aside_empty_spouses')}</p>
            ) : (
              <ul className="space-y-2">
                {sortedMarriages.map((m) => {
                  const otherId = m.person1Id === personId ? m.person2Id : m.person1Id
                  const label = spouseLabelOf(m)
                  const kinshipTerm = label.values ? t(label.key, label.values) : t(label.key)
                  return (
                    <li key={m.id}>
                      <RelationshipRow
                        kinshipTerm={kinshipTerm}
                        person={personById.get(otherId) ?? null}
                        personId={otherId}
                        typeChip={t(m.status)}
                      />
                    </li>
                  )
                })}
              </ul>
            )}
          </section>

          <section className="space-y-2" aria-labelledby="relationships-aside-parents">
            <h3
              id="relationships-aside-parents"
              className="text-muted-foreground text-xs font-medium uppercase"
            >
              {t('aside_parents')}
            </h3>
            {parents.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('aside_empty_parents')}</p>
            ) : (
              <ul className="space-y-2">
                {parents.map((p) => (
                  <li key={p.id}>
                    <RelationshipRow
                      kinshipTerm={t('parent')}
                      person={personById.get(p.parentId) ?? null}
                      personId={p.parentId}
                      typeChip={t(parentChildTypeKey(p))}
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-2" aria-labelledby="relationships-aside-children">
            <h3
              id="relationships-aside-children"
              className="text-muted-foreground text-xs font-medium uppercase"
            >
              {t('aside_children')}
            </h3>
            {children.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('aside_empty_children')}</p>
            ) : (
              <ul className="space-y-2">
                {children.map((c) => (
                  <li key={c.id}>
                    <RelationshipRow
                      kinshipTerm={t('child')}
                      person={personById.get(c.childId) ?? null}
                      personId={c.childId}
                      typeChip={t(parentChildTypeKey(c))}
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </aside>
  )
}

function collectOtherIds(
  targetPersonId: string,
  marriages: readonly Marriage[],
  parentChild: readonly ParentChild[],
): string[] {
  const set = new Set<string>()
  for (const m of marriages) {
    set.add(m.person1Id === targetPersonId ? m.person2Id : m.person1Id)
  }
  for (const row of parentChild) {
    if (row.parentId === targetPersonId) set.add(row.childId)
    else if (row.childId === targetPersonId) set.add(row.parentId)
  }
  set.delete(targetPersonId)
  return [...set]
}

function indexById(people: readonly Person[]): Map<string, Person> {
  const map = new Map<string, Person>()
  for (const p of people) map.set(p.id, p)
  return map
}

/**
 * `adoptive` is the message key the existing catalog uses for `adopted`
 * edges (`web/messages/<locale>.json` → `relationship.adoptive`). The
 * mapping is kept narrow to this component so the domain/wire layer keeps
 * naming the backend's `adopted` as it stands.
 */
function parentChildTypeKey(row: ParentChild): string {
  return row.relationshipType === 'adopted' ? 'adoptive' : row.relationshipType
}
