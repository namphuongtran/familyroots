'use client'

/**
 * Spec §7.7c, "người khác vừa sửa" — the field-level conflict resolution
 * dialog for a `409 stale_write` (ADR-017). The most detailed screen this
 * seed builds, because a form that swallows this code loses a clan member's
 * work silently.
 *
 * **First use of `@radix-ui/react-dialog` in `web/src`** (`web/CLAUDE.md`
 * §4 / `.claude/rules/tailwind.md` §4: the package was installed and
 * imported by no file). The pattern: `Dialog.Root` controlled by the
 * caller's own `open` state (never uncontrolled — the caller owns whether a
 * conflict exists), `onEscapeKeyDown` and `onInteractOutside` both call
 * `event.preventDefault()` so the dialog is exactly as undismissable as
 * spec §7.7c requires ("not dismissible by scrim tap"), and `Dialog.Title`/
 * `Dialog.Description` carry the real heading and body text rather than
 * `aria-label`s, so a screen reader gets the same two sentences a sighted
 * user does.
 */

import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useTranslations } from 'next-intl'
import type { FieldChoice, FieldDiffRow } from './stale-write-diff'

interface StaleWriteDialogProps {
  open: boolean
  personName: string
  rows: FieldDiffRow[]
  /** Spec §7.7c: "If the resubmit 409s again, reopen the dialog ... and add [this note]." */
  repeatedConflict: boolean
  choices: Record<string, FieldChoice>
  onChoiceChange: (field: string, choice: FieldChoice) => void
  onSaveResolved: () => void
  onDiscardReload: () => void
  /** Resolves `true` only when the copy actually reached the clipboard — the confirmation is not shown on a lie. */
  onCopyMine: () => Promise<boolean>
  /** Same text `onCopyMine` tries to put on the clipboard — the manual fallback when that fails (no Clipboard API, insecure context, permission denied). */
  copyText: string
  saving: boolean
}

function SegmentedChoice({
  field,
  choice,
  onChoiceChange,
  mineLabel,
  latestLabel,
}: {
  field: string
  choice: FieldChoice
  onChoiceChange: (field: string, choice: FieldChoice) => void
  mineLabel: string
  latestLabel: string
}) {
  return (
    <div role="radiogroup" aria-label={field} className="mt-2 flex flex-wrap gap-2">
      {(['mine', 'latest'] as const).map((value) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={choice === value}
          onClick={() => onChoiceChange(field, value)}
          className={
            choice === value
              ? 'bg-primary text-primary-foreground rounded-full px-3 py-1 text-xs font-medium'
              : 'border-input text-foreground hover:bg-muted rounded-full border px-3 py-1 text-xs transition-colors'
          }
        >
          {value === 'mine' ? mineLabel : latestLabel}
        </button>
      ))}
    </div>
  )
}

export function StaleWriteDialog({
  open,
  personName,
  rows,
  repeatedConflict,
  choices,
  onChoiceChange,
  onSaveResolved,
  onDiscardReload,
  onCopyMine,
  copyText,
  saving,
}: StaleWriteDialogProps) {
  const t = useTranslations('member_form')
  const [copyResult, setCopyResult] = useState<'idle' | 'copied' | 'failed'>('idle')

  return (
    <Dialog.Root open={open}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content
          className="bg-card fixed top-1/2 left-1/2 max-h-[85vh] w-[calc(100%-2rem)] max-w-[560px] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl p-6"
          onEscapeKeyDown={(event) => event.preventDefault()}
          onInteractOutside={(event) => event.preventDefault()}
          onPointerDownOutside={(event) => event.preventDefault()}
        >
          <Dialog.Title className="text-foreground font-serif text-lg">
            {t('stale_write_title')}
          </Dialog.Title>
          <Dialog.Description className="text-muted-foreground mt-2 text-sm">
            {t('stale_write_body', { name: personName })}
          </Dialog.Description>

          {repeatedConflict && (
            <p className="bg-accent text-accent-foreground mt-3 rounded-xl p-3 text-sm">
              {t('stale_write_repeated_note')}
            </p>
          )}

          <ul className="mt-4 space-y-4">
            {rows.map((row) => (
              <li key={row.field} className="bg-muted rounded-2xl p-3">
                <p className="text-foreground text-sm font-semibold">{row.label}</p>
                {/*
                  Stacked (label above value), not the side-by-side
                  `justify-between` row spec's own diagram shows — measured
                  in a real browser at 320px/200% text scale: a flex row's
                  value span defaults to `min-width: auto`, which sizes it to
                  its own longest unbroken run rather than letting it wrap,
                  so a long note or biography value overflowed the dialog by
                  38px with no page-level scrollbar to reveal it (Radix's
                  `overflow-y-auto` computes `overflow-x` to `auto` too per
                  the CSS spec, so the overflow was invisible, not merely
                  ugly). Stacking removes the flex min-width trap entirely —
                  a block element wraps at its container's width regardless
                  of content length.
                */}
                <div className="mt-2 space-y-2 text-sm">
                  <div>
                    <span className="text-muted-foreground block text-xs">{t('your_version')}</span>
                    <span className="text-foreground">
                      {row.mine || t('empty_value_placeholder')}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block text-xs">
                      {t('latest_version')}
                    </span>
                    <span className="text-foreground">
                      {row.latest || t('empty_value_placeholder')}
                    </span>
                  </div>
                </div>
                <SegmentedChoice
                  field={row.field}
                  choice={choices[row.field] ?? row.defaultChoice}
                  onChoiceChange={onChoiceChange}
                  mineLabel={t('keep_mine')}
                  latestLabel={t('use_latest')}
                />
              </li>
            ))}
          </ul>

          <div className="mt-6 flex flex-col gap-2">
            <button
              type="button"
              onClick={onSaveResolved}
              disabled={saving}
              className="bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring rounded-full px-4 py-2 text-sm font-medium transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none disabled:opacity-60"
            >
              {saving ? t('saving') : t('save_resolved')}
            </button>
            <button
              type="button"
              onClick={onDiscardReload}
              className="text-foreground hover:bg-muted rounded-full px-4 py-2 text-sm transition-colors"
            >
              {t('discard_reload')}
            </button>
            <button
              type="button"
              onClick={async () => {
                const ok = await onCopyMine()
                setCopyResult(ok ? 'copied' : 'failed')
              }}
              className="text-foreground hover:bg-muted rounded-full px-4 py-2 text-sm transition-colors"
            >
              {t('copy_mine')}
            </button>
            {copyResult === 'copied' && (
              <p role="status" className="text-muted-foreground text-center text-xs">
                {t('copied_confirmation')}
              </p>
            )}
            {copyResult === 'failed' && (
              <div>
                <p className="text-muted-foreground text-center text-xs">
                  {t('copy_failed_fallback')}
                </p>
                <textarea
                  readOnly
                  value={copyText}
                  rows={4}
                  className="border-input bg-background mt-1 w-full rounded-lg border p-2 text-xs"
                  onFocus={(event) => event.currentTarget.select()}
                />
              </div>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
