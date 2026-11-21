'use client'

import { memo } from 'react'
import { useTranslations } from 'next-intl'
import { Handle, Position } from '@xyflow/react'
import { PersonAvatar } from '@/features/persons'
import { cn } from '@/lib/utils/cn'
import { GenerationBadge } from './GenerationBadge'
import type { PersonNodeData } from './tree-layout'

/**
 * One person on the canvas. Clicking selects it (the canvas's `onNodeClick`); the focus panel
 * then opens. Gender is not encoded in colour (ADR-055). A pedigree-collapse stub renders in full,
 * never greyed, with the `Nhánh chính ở nơi khác` chip (spec § 3.4).
 */
export const PersonNode = memo(function PersonNode({ data }: { data: PersonNodeData }) {
  const t = useTranslations('tree')

  return (
    <div
      className={cn(
        'relative flex cursor-pointer flex-col items-center gap-1 rounded-xl border-2 p-2',
        'border-border bg-card w-36 shadow-xs transition-all hover:shadow-md',
        data.isSelected && 'ring-ring ring-2 ring-offset-1',
        data.isDeceased && !data.isPedigreeStub && 'opacity-70',
      )}
    >
      {/* The founder state as a glyph, not a colour (T-06). */}
      {data.isFounder && <span className="absolute -top-2 text-xs">👑</span>}

      <Handle type="target" position={Position.Top} className="bg-muted-foreground! h-2! w-2!" />

      <PersonAvatar
        avatarUrl={data.avatarUrl}
        fullName={data.fullName}
        size="xs"
        isDeceased={data.isDeceased}
      />

      <div className="w-full min-w-0 text-center">
        <p className="text-foreground truncate text-[11px] leading-tight font-semibold">
          {data.fullName}
        </p>
        {data.birthYear && (
          <p className="text-muted-foreground text-[9px]">
            {data.birthYear}
            {data.deathYear ? ` – ${data.deathYear}` : ''}
          </p>
        )}
      </div>

      {data.generation !== undefined && <GenerationBadge generation={data.generation} />}
      {data.isPedigreeStub && (
        <span className="bg-muted text-muted-foreground rounded-full px-2 text-[9px]">
          {t('pedigree_stub')}
        </span>
      )}

      <Handle type="source" position={Position.Bottom} className="bg-muted-foreground! h-2! w-2!" />
    </div>
  )
})
