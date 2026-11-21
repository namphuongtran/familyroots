'use client'

import Link from 'next/link'
import * as Dialog from '@radix-ui/react-dialog'
import { useLocale, useTranslations } from 'next-intl'

export type NodeAction = 'add_child' | 'add_spouse'

interface NodeActionsSheetProps {
  readonly personId: string
  readonly fullName: string
  /** `createRelationship` (rbac.md): an editor or admin. A viewer gets only "Xem hồ sơ". */
  readonly canAddRelationships: boolean
  readonly onAction: (action: NodeAction) => void
  readonly onClose: () => void
}

const itemClass =
  'bg-muted text-foreground hover:bg-primary-container focus:ring-ring block w-full rounded-xl px-4 py-3 text-left text-sm transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none'

/**
 * Spec §3.5's tree node long-press sheet. #328 builds the two actions that open the relationship
 * editor, "Thêm con" and "Thêm vợ/chồng", beside "Xem hồ sơ". The rule is remove, not disable:
 * without `canAddRelationships` the two are not rendered at all. The other spec actions (Sửa,
 * Đặt thủy tổ, Tìm quan hệ, Đề nghị sửa) are not part of this issue.
 */
export function NodeActionsSheet({
  personId,
  fullName,
  canAddRelationships,
  onAction,
  onClose,
}: NodeActionsSheetProps) {
  const t = useTranslations('tree')
  const tRel = useTranslations('relationship')
  const locale = useLocale()

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="bg-scrim fixed inset-0 z-40" />
        <Dialog.Content className="bg-card fixed inset-x-0 bottom-0 z-50 mx-auto w-full max-w-md space-y-3 rounded-t-2xl p-6">
          <Dialog.Title className="text-foreground font-serif text-lg break-words">
            {fullName}
          </Dialog.Title>
          <Dialog.Description className="sr-only">{t('node_actions')}</Dialog.Description>
          <ul className="space-y-2">
            <li>
              <Link href={`/${locale}/members/${personId}`} className={itemClass}>
                {t('view_profile')}
              </Link>
            </li>
            {canAddRelationships && (
              <>
                <li>
                  <button type="button" onClick={() => onAction('add_child')} className={itemClass}>
                    {tRel('add_child')}
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => onAction('add_spouse')}
                    className={itemClass}
                  >
                    {tRel('add_spouse')}
                  </button>
                </li>
              </>
            )}
          </ul>
          <Dialog.Close className="text-foreground hover:bg-muted w-full rounded-full px-4 py-2 text-sm transition-colors">
            {t('close')}
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
