'use client'

import { useTranslations } from 'next-intl'
import { getMarriageStatusLabel, getParentChildTypeLabel } from '@/lib/utils/kinship'
import type { PathStep } from '@/lib/types'

interface RelationshipPathProps {
  steps: PathStep[]
  fromName: string
  toName: string
}

export function RelationshipPath({ steps, fromName, toName }: RelationshipPathProps) {
  const t = useTranslations('tree')

  if (steps.length === 0) {
    return (
      <p className="text-sm text-gray-400 italic">{t('no_path')}</p>
    )
  }

  return (
    <div className="space-y-1">
      <p className="text-sm font-medium text-gray-700">
        {t('path_from')} <span className="text-primary">{fromName}</span> {t('path_to')}{' '}
        <span className="text-primary">{toName}</span>
      </p>
      <ol className="list-none space-y-0.5">
        {steps.map((step, i) => (
          <li key={i} className="flex items-center gap-2 text-sm text-gray-600">
            <span className="w-4 h-4 flex items-center justify-center rounded-full bg-primary-container text-primary-container-foreground text-[10px] font-bold shrink-0">
              {i + 1}
            </span>
            <span>
              {step.full_name}
              <span className="text-gray-400 ml-1">({step.edge_type === 'spouse' ? getMarriageStatusLabel(step.edge_subtype) : getParentChildTypeLabel(step.edge_subtype)})</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}
