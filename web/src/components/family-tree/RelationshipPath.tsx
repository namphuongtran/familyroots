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
    return <p className="text-sm text-gray-400 italic">{t('no_path')}</p>
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
            <span className="bg-primary-container text-primary-container-foreground flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold">
              {i + 1}
            </span>
            <span>
              {step.full_name}
              <span className="ml-1 text-gray-400">
                (
                {step.edge_type === 'spouse'
                  ? getMarriageStatusLabel(step.edge_subtype)
                  : getParentChildTypeLabel(step.edge_subtype)}
                )
              </span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}
