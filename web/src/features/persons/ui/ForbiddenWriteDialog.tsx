'use client'

/**
 * Spec §7.7c's last paragraph: "if a role is downgraded mid-edit, the save
 * returns 403 and the dialog explains it plainly with a `Sao chép nội dung
 * của tôi` escape." A much smaller dialog than `StaleWriteDialog` — there is
 * nothing to merge, because the caller can no longer write at all — so it is
 * its own component rather than a second mode grafted onto that one.
 */

import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useTranslations } from 'next-intl'

interface ForbiddenWriteDialogProps {
  open: boolean
  onCopyMine: () => Promise<boolean>
  onClose: () => void
}

export function ForbiddenWriteDialog({ open, onCopyMine, onClose }: ForbiddenWriteDialogProps) {
  const t = useTranslations('member_form')
  const [copied, setCopied] = useState(false)

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="bg-card fixed top-1/2 left-1/2 w-[calc(100%-2rem)] max-w-[480px] -translate-x-1/2 -translate-y-1/2 rounded-2xl p-6">
          <Dialog.Title className="text-foreground font-serif text-lg">
            {t('forbidden_title')}
          </Dialog.Title>
          <Dialog.Description className="text-muted-foreground mt-2 text-sm">
            {t('forbidden_body')}
          </Dialog.Description>
          <div className="mt-6 flex flex-col gap-2">
            <button
              type="button"
              onClick={async () => setCopied(await onCopyMine())}
              className="border-input text-foreground hover:bg-muted rounded-full border px-4 py-2 text-sm transition-colors"
            >
              {t('copy_mine')}
            </button>
            {copied && (
              <p role="status" className="text-muted-foreground text-center text-xs">
                {t('copied_confirmation')}
              </p>
            )}
            <Dialog.Close asChild>
              <button
                type="button"
                className="bg-primary text-primary-foreground hover:bg-primary-hover rounded-full px-4 py-2 text-sm font-medium transition-colors"
              >
                {t('close')}
              </button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
