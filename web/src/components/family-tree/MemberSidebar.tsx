'use client'

import Link from 'next/link'
import { X, Edit, Users } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { MemberAvatar } from '@/components/members/MemberAvatar'
import { formatLifespan } from '@/lib/utils/date'
import { Skeleton } from '@/components/ui/skeleton'
import { useMember } from '@/lib/hooks/useMembers'

interface MemberSidebarProps {
  memberId: string
  onClose: () => void
}

export function MemberSidebar({ memberId, onClose }: MemberSidebarProps) {
  const t = useTranslations('member')
  const { data: member, isLoading } = useMember(memberId)

  return (
    <div className="absolute top-4 left-4 z-20 bg-white rounded-xl shadow-lg border border-gray-200 w-64 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-100">
        <span className="text-sm font-semibold text-gray-700">{t('details')}</span>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
          <X className="h-4 w-4" />
        </button>
      </div>

      {isLoading ? (
        <div className="p-4 space-y-3">
          <div className="flex items-center gap-3">
            <Skeleton className="h-12 w-12 rounded-full shrink-0" />
            <div className="space-y-1 flex-1">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-3 w-20" />
            </div>
          </div>
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-3/4" />
        </div>
      ) : member ? (
        <div className="p-4 space-y-3">
          <div className="flex items-center gap-3">
            <MemberAvatar
              avatarUrl={member.avatar_url}
              fullName={member.full_name}
              gender={member.gender}
              size="md"
              isDeceased={!!member.death_date}
            />
            <div>
              <p className="text-sm font-semibold text-gray-800">{member.full_name}</p>
              <p className="text-xs text-gray-500">
                {formatLifespan(member.birth_date, member.death_date, member.birth_date_approx)}
              </p>
            </div>
          </div>

          {member.birth_place && (
            <div className="text-xs text-gray-600">
              <span className="font-medium">{t('born_in')}: </span>
              {member.birth_place}
            </div>
          )}

          {member.generation && (
            <div className="text-xs text-gray-600">
              <span className="font-medium">{t('generation')}: </span>
              {member.generation}
            </div>
          )}

          {member.notes && (
            <p className="text-xs text-gray-500 italic line-clamp-3">{member.notes}</p>
          )}

          <div className="flex gap-2 pt-1">
            <Link
              href={`/members/${member.id}`}
              className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 text-xs rounded-md bg-primary-50 text-primary-700 hover:bg-primary-100 transition-colors"
            >
              <Users className="h-3 w-3" />
              {t('view_profile')}
            </Link>
            <Link
              href={`/members/${member.id}/edit`}
              className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 text-xs rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
            >
              <Edit className="h-3 w-3" />
              {t('edit')}
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  )
}
