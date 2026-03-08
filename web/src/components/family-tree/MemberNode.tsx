'use client'

import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import { useRouter } from 'next/navigation'
import { MemberAvatar } from '@/components/members/MemberAvatar'
import { cn } from '@/lib/utils/cn'
import type { TreeNode } from '@/lib/types'

export type MemberNodeData = TreeNode & { isSelected?: boolean; [key: string]: unknown }

export const MemberNode = memo(function MemberNode({ data, selected }: { data: MemberNodeData; selected?: boolean }) {
  const router = useRouter()
  const isDeceased = !!data.death_date
  const isFounder = data.generation === 1

  const borderColor =
    data.gender === 'male'
      ? 'border-blue-400'
      : data.gender === 'female'
        ? 'border-pink-400'
        : 'border-gray-300'

  return (
    <div
      onClick={() => router.push(`/members/${data.id}`)}
      className={cn(
        'relative flex flex-col items-center gap-1 p-2 rounded-xl border-2 cursor-pointer',
        'bg-white shadow-sm hover:shadow-md transition-all w-36',
        borderColor,
        selected && 'ring-2 ring-primary-400 ring-offset-1',
        isDeceased && 'opacity-70',
      )}
    >
      {isFounder && (
        <span className="absolute -top-2 text-gold-500 text-xs">👑</span>
      )}

      <Handle type="target" position={Position.Top} className="!bg-gray-400 !w-2 !h-2" />

      <MemberAvatar
        avatarUrl={data.avatar_url ?? undefined}
        fullName={data.full_name}
        gender={data.gender}
        size="sm"
        isDeceased={isDeceased}
      />

      <div className="text-center min-w-0 w-full">
        <p className="text-[11px] font-semibold text-gray-800 truncate leading-tight">
          {data.full_name}
        </p>
        {data.birth_date && (
          <p className="text-[9px] text-gray-400">
            {data.birth_date.slice(0, 4)}
            {data.death_date ? ` – ${data.death_date.slice(0, 4)}` : ''}
          </p>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} className="!bg-gray-400 !w-2 !h-2" />
    </div>
  )
})
