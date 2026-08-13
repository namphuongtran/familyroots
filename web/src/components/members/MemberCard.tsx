'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { MemberAvatar } from './MemberAvatar'
import { formatLifespan } from '@/lib/utils/date'
import { cn } from '@/lib/utils/cn'
import type { PersonSummary } from '@/lib/types'

interface MemberCardProps {
  member: PersonSummary
  className?: string
}

export function MemberCard({ member, className }: MemberCardProps) {
  const t = useTranslations('member')
  const isDeceased = !!member.death_date

  return (
    <Link
      href={`/persons/${member.id}`}
      className={cn(
        'flex items-center gap-3 p-3 rounded-lg border border-cream-200 hover:border-primary',
        'hover:shadow-xs transition-all bg-white cursor-pointer',
        className,
      )}
    >
      <MemberAvatar
        avatarUrl={member.avatar_url}
        fullName={member.full_name}
        gender={member.gender}
        size="md"
        isDeceased={isDeceased}
      />

      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-800 truncate">
          {member.full_name}
        </p>
        <p className="text-xs text-gray-500">
          {formatLifespan(member.birth_date, member.death_date, member.birth_date_approx)}
        </p>
        {isDeceased && (
          <span className="text-[10px] text-gray-400">{t('deceased')}</span>
        )}
      </div>

      {member.generation != null && (
        <span className="text-[10px] bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded shrink-0">
          {t('generation_badge', { gen: member.generation })}
        </span>
      )}
    </Link>
  )
}
