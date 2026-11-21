'use client'

import { useId, useState } from 'react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils/cn'

/**
 * The đời badge, design spec § 3.2. A known đời reads `Đời {n}` on `heritage-container`; a
 * `null` đời reads `Đời ?` on the muted ground. It is never omitted, never `Đời 0`, never guessed.
 *
 * With `explainable`, `Đời ?` is a button that opens the one-paragraph explainer. On the canvas it
 * is plain text, because the node itself is the click target there.
 */
export function GenerationBadge({
  generation,
  explainable = false,
  className,
}: {
  generation: number | null
  explainable?: boolean
  className?: string
}) {
  const t = useTranslations('tree')
  const [open, setOpen] = useState(false)
  const explainerId = useId()

  if (generation !== null) {
    return (
      <span
        aria-label={t('generation_sr', { n: generation })}
        className={cn(
          'bg-heritage-container text-heritage-container-foreground inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums',
          className,
        )}
      >
        {t('generation_badge', { n: generation })}
      </span>
    )
  }

  const badgeClass = cn(
    'bg-muted text-muted-foreground inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold',
    className,
  )

  if (!explainable) {
    return (
      <span aria-label={t('generation_unknown_sr')} className={badgeClass}>
        {t('generation_unknown')}
      </span>
    )
  }

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        aria-label={t('generation_unknown_sr')}
        aria-expanded={open}
        aria-controls={explainerId}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          badgeClass,
          'focus:ring-ring focus:ring-2 focus:ring-offset-2 focus:outline-none',
        )}
      >
        {t('generation_unknown')}
      </button>
      {open && (
        <span id={explainerId} className="text-muted-foreground text-xs">
          {t('generation_unknown_explainer')}
        </span>
      )}
    </span>
  )
}
