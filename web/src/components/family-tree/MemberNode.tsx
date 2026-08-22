'use client'

import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import { useRouter } from 'next/navigation'
import { MemberAvatar } from '@/components/members/MemberAvatar'
import { cn } from '@/lib/utils/cn'
import type { TreeNode } from '@/lib/types'

export type MemberNodeData = TreeNode & { isSelected?: boolean; [key: string]: unknown }

export const MemberNode = memo(function MemberNode({
  data,
  selected,
}: {
  data: MemberNodeData
  selected?: boolean
}) {
  const router = useRouter()
  const isDeceased = !!data.death_date
  const isFounder = data.generation === 1

  return (
    <div
      onClick={() => router.push(`/persons/${data.id}`)}
      className={cn(
        'relative flex cursor-pointer flex-col items-center gap-1 rounded-xl border-2 p-2',
        // ADR-055: the border used to carry `border-blue-400` / `border-pink-400`
        // for male/female, with no other channel — gender had no text or icon
        // anywhere on this node, so colour was T-06's forbidden *only* channel,
        // and both hexes could not flip with the colour scheme besides. The
        // decision is to stop encoding gender in border colour rather than add
        // a token: every node now takes the same `border-border` a `data.gender`
        // of `'unknown'` already used.
        'border-border w-36 bg-white shadow-xs transition-all hover:shadow-md',
        selected && 'ring-ring ring-2 ring-offset-1',
        isDeceased && 'opacity-70',
      )}
    >
      {/*
        The crown carries the founder state as a glyph, not as a colour, which is
        what T-06 asks for. It used to carry `text-gold-500` as well; that class
        was removed by S-003 because gold is never a text colour, and it painted
        nothing anyway: a colour emoji font supplies its own colours and ignores
        `color`.
      */}
      {isFounder && <span className="absolute -top-2 text-xs">👑</span>}

      <Handle type="target" position={Position.Top} className="bg-muted-foreground! h-2! w-2!" />

      <MemberAvatar
        avatarUrl={data.avatar_url ?? undefined}
        fullName={data.full_name}
        gender={data.gender}
        size="sm"
        isDeceased={isDeceased}
      />

      <div className="w-full min-w-0 text-center">
        <p className="text-foreground truncate text-[11px] leading-tight font-semibold">
          {data.full_name}
        </p>
        {data.birth_date && (
          <p className="text-muted-foreground text-[9px]">
            {data.birth_date.slice(0, 4)}
            {data.death_date ? ` – ${data.death_date.slice(0, 4)}` : ''}
          </p>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} className="bg-muted-foreground! h-2! w-2!" />
    </div>
  )
})
