'use client'

import { useMemo } from 'react'
import { useTranslations } from 'next-intl'
import type { TreePerson } from '@/domain/tree/tree'
import { GenerationBadge } from './GenerationBadge'
import { treeToOutline, type OutlineGroup, type OutlinePerson } from './tree-outline'

const ENTRY_CLASS =
  'hover:bg-card focus:ring-ring inline-flex min-h-11 flex-wrap items-center gap-2 rounded-md px-2 py-1 text-left text-sm focus:ring-2 focus:ring-offset-2 focus:outline-none'

/**
 * Spec T-08: the canvas's accessible equivalent. The same people the canvas draws, as a nested
 * list: each entry a button (Tab reaches it, Enter or Space opens the focus panel), each lineage
 * entry speaking its đời through `GenerationBadge`, and each father's children under the § 3.3
 * wife groups `WifeGroups` uses.
 */
export function TreeListView({
  root,
  onSelectPerson,
}: {
  root: TreePerson
  onSelectPerson: (personId: string) => void
}) {
  const t = useTranslations('tree')
  const outline = useMemo(() => treeToOutline(root), [root])

  return (
    <div className="h-full overflow-y-auto px-4 pb-8">
      <ul aria-label={t('list_view_label')} className="space-y-1">
        <PersonItem person={outline} onSelectPerson={onSelectPerson} />
      </ul>
    </div>
  )
}

function PersonItem({
  person,
  onSelectPerson,
}: {
  person: OutlinePerson
  onSelectPerson: (personId: string) => void
}) {
  const t = useTranslations('tree')

  return (
    <li>
      <button
        type="button"
        data-person-id={person.personId}
        onClick={() => onSelectPerson(person.personId)}
        className={ENTRY_CLASS}
      >
        <span className="text-foreground font-semibold">{person.fullName}</span>{' '}
        <GenerationBadge generation={person.generation} />{' '}
        {person.isPedigreeStub && (
          <span className="bg-muted text-muted-foreground rounded-full px-2 text-[11px]">
            {t('pedigree_stub')}
          </span>
        )}
      </button>

      {person.spouses.length > 0 && (
        <div className="ml-4">
          <p className="text-muted-foreground px-2 text-xs">{t('spouses')}</p>
          <ul aria-label={t('spouses_of', { name: person.fullName })}>
            {person.spouses.map((spouse) => (
              <li key={spouse.key}>
                <button
                  type="button"
                  data-person-id={spouse.personId}
                  onClick={() => onSelectPerson(spouse.personId)}
                  className={ENTRY_CLASS}
                >
                  <span className="text-foreground">{spouse.fullName}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {person.groups.length > 0 && (
        <ul aria-label={t('children_of', { name: person.fullName })} className="ml-4 space-y-2">
          {person.groups.map((group) => (
            <GroupItem key={group.key} group={group} onSelectPerson={onSelectPerson} />
          ))}
        </ul>
      )}
    </li>
  )
}

function GroupItem({
  group,
  onSelectPerson,
}: {
  group: OutlineGroup
  onSelectPerson: (personId: string) => void
}) {
  const t = useTranslations('tree')
  const label =
    group.kind === 'wife'
      ? [
          group.order !== null ? t('wife_order', { order: String(group.order) }) : null,
          group.motherName ?? t('wife_unnamed'),
        ]
          .filter(Boolean)
          .join(' · ')
      : t('unknown_mother')

  return (
    <li className="bg-muted rounded-lg p-2">
      <p className="text-foreground text-xs font-semibold">{label}</p>
      <ul aria-label={label} className="mt-1 space-y-1">
        {group.children.map((child) => (
          <PersonItem key={child.key} person={child} onSelectPerson={onSelectPerson} />
        ))}
      </ul>
    </li>
  )
}
