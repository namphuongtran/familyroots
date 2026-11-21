'use client'

import { useMemo, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils/cn'
import { useClientRequestContext } from '@/shared/http/context.client'
import { usePersonMarriages } from '../hooks/use-relationship-queries'
import { useRelatedPeople } from '../hooks/use-related-people'
import { SpousesSection } from './SpousesSection'
import { AddChildSection, AddSpouseSection, ParentsSection } from './CreateSections'

export type RelationshipEditorSection = 'spouses' | 'add_spouse' | 'parents' | 'add_child'

const SECTIONS: readonly RelationshipEditorSection[] = [
  'spouses',
  'add_spouse',
  'parents',
  'add_child',
]

interface RelationshipEditorSheetProps {
  readonly personId: string
  /** Shown in the title, when the caller knows it. */
  readonly personName?: string | null
  readonly open: boolean
  readonly onOpenChange: (open: boolean) => void
  /** Which part opens first: the tree's "Thêm con" and "Thêm vợ/chồng" open their own. */
  readonly initialSection?: RelationshipEditorSection
  /** Every successful write, for a caller that holds data this slice does not (the tree). */
  readonly onChanged?: () => void
}

interface Notice {
  readonly id: number
  readonly text: string
  readonly warning: boolean
}

/**
 * The relationship editor (#328, decided on #310): a side sheet for an editor or admin. The
 * caller decides who sees an entry point; the backend refuses a viewer's write anyway (403,
 * shown as `forbidden`). Every write goes through this slice's repository, and every PATCH sends
 * the ADR-017 version.
 *
 * **The toast is local to the sheet.** No toast primitive exists in `web/src` (the persons form
 * decided the same, `PersonForm.tsx`), so a successful write shows a `role="status"` line at the
 * top of the sheet, in the warning colours with the backend's `meta.warning` when it carried one
 * (spec §7.7a: the save succeeds, and the warning appears after it).
 */
export function RelationshipEditorSheet({
  personId,
  personName,
  open,
  onOpenChange,
  initialSection = 'spouses',
  onChanged,
}: RelationshipEditorSheetProps) {
  const t = useTranslations('relationship_editor')
  const tRel = useTranslations('relationship')
  const { context, ready, refreshAuth } = useClientRequestContext()
  const [section, setSection] = useState<RelationshipEditorSection>(initialSection)
  const [notice, setNotice] = useState<Notice | null>(null)

  const marriagesQuery = usePersonMarriages(personId, {
    context,
    refreshAuth,
    enabled: ready && open,
  })
  const marriages = useMemo(() => marriagesQuery.data ?? [], [marriagesQuery.data])
  const spouseIds = useMemo(
    () => marriages.map((m) => (m.person1Id === personId ? m.person2Id : m.person1Id)),
    [marriages, personId],
  )
  const people = useRelatedPeople(spouseIds, { context, refreshAuth, enabled: ready && open })

  function onSaved(warning: string | null) {
    setNotice((n) => ({
      id: (n?.id ?? 0) + 1,
      text: warning ? t('saved_with_warning', { warning }) : t('saved'),
      warning: warning !== null,
    }))
    onChanged?.()
  }

  const shared = { personId, context, refreshAuth, ready, onSaved }

  let body
  if (!ready || marriagesQuery.isLoading) {
    body = <p className="text-muted-foreground text-sm">{tRel('aside_loading')}</p>
  } else if (marriagesQuery.isError) {
    body = <p className="text-destructive text-sm">{tRel('aside_error')}</p>
  } else if (section === 'spouses') {
    body = (
      <SpousesSection
        personId={personId}
        marriages={marriages}
        people={people}
        context={context}
        refreshAuth={refreshAuth}
        onSaved={onSaved}
      />
    )
  } else if (section === 'add_spouse') {
    body = <AddSpouseSection {...shared} marriages={marriages} />
  } else if (section === 'parents') {
    body = <ParentsSection {...shared} />
  } else {
    body = <AddChildSection {...shared} />
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="bg-scrim fixed inset-0 z-40" />
        <Dialog.Content className="bg-card fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col overflow-y-auto p-6 sm:rounded-l-2xl">
          <div className="flex flex-wrap-reverse items-start justify-between gap-2">
            <div className="min-w-0 flex-1 basis-40">
              <Dialog.Title className="text-foreground font-serif text-lg break-words">
                {personName ? t('sheet_title_named', { name: personName }) : t('sheet_title')}
              </Dialog.Title>
              <Dialog.Description className="text-muted-foreground mt-1 text-sm">
                {t('sheet_description')}
              </Dialog.Description>
            </div>
            <Dialog.Close
              aria-label={t('close')}
              className="text-muted-foreground hover:text-foreground focus:ring-ring rounded-full p-2 transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </Dialog.Close>
          </div>

          <div role="group" aria-label={t('sections')} className="mt-4 flex flex-wrap gap-2">
            {SECTIONS.map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={section === value}
                onClick={() => {
                  setSection(value)
                  setNotice(null)
                }}
                className={cn(
                  'focus:ring-ring rounded-full px-3 py-2 text-sm transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none',
                  section === value
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-foreground hover:bg-primary-container',
                )}
              >
                {t(`tab_${value}`)}
              </button>
            ))}
          </div>

          {notice && (
            <p
              key={notice.id}
              role="status"
              className={cn(
                'mt-4 rounded-xl p-3 text-sm',
                notice.warning
                  ? 'bg-warning-container text-warning-container-foreground'
                  : 'bg-success-container text-success-container-foreground',
              )}
            >
              {notice.text}
            </p>
          )}

          <div className="mt-4">{body}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
