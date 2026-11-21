'use client'

import { useTranslations } from 'next-intl'
import type { TreePerson } from '@/domain/tree/tree'
import { groupChildrenByMother } from '@/domain/kinship/wife-groups'
import { GenerationBadge } from './GenerationBadge'

/**
 * A father's children grouped by wife, design spec § 3.3. Each group's header is the order chip
 * (`Vợ cả`, `Vợ hai`, …, none when `mother_spouse_order` is unknown) and the wife's name; children
 * with no recorded mother close the list under `Chưa rõ mẹ`. Groups are separated by a background
 * step and spacing, never a rule, and every group gets the same treatment.
 */
export function WifeGroups({
  parent,
  onSelectPerson,
}: {
  parent: TreePerson
  onSelectPerson: (personId: string) => void
}) {
  const t = useTranslations('tree')
  const groups = groupChildrenByMother(parent.children, parent.spouses)

  if (groups.length === 0) {
    return <p className="text-muted-foreground text-xs">{t('no_children')}</p>
  }

  return (
    <div className="space-y-4">
      {groups.map((group) => {
        const key = group.kind === 'wife' ? group.motherId : 'unknown-mother'
        return (
          <section key={key} className="bg-muted rounded-lg p-2">
            <h4 className="text-foreground flex flex-wrap items-center gap-1 text-xs font-semibold">
              {group.kind === 'wife' ? (
                <>
                  {group.order !== null && (
                    <span className="bg-card text-muted-foreground rounded-full px-2 py-0.5 text-[11px]">
                      {t('wife_order', { order: String(group.order) })}
                    </span>
                  )}
                  <span>{group.motherName ?? t('wife_unnamed')}</span>
                </>
              ) : (
                <span>{t('unknown_mother')}</span>
              )}
            </h4>
            <ul className="mt-1 space-y-1">
              {group.children.map((child, i) => (
                <li key={`${child.id}-${i}`}>
                  <button
                    type="button"
                    onClick={() => onSelectPerson(child.id)}
                    className="hover:bg-card focus:ring-ring flex w-full flex-wrap items-center justify-between gap-1 rounded-md px-2 py-1 text-left text-xs focus:ring-2 focus:ring-offset-2 focus:outline-none"
                  >
                    <span className="text-foreground">{child.fullName}</span>
                    <GenerationBadge generation={child.generation} />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
