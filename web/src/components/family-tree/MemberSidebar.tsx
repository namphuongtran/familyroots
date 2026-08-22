'use client'

import Link from 'next/link'
import { X, Edit, Users } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { MemberAvatar } from '@/components/members/MemberAvatar'
import { formatLifespan } from '@/lib/utils/date'
import { Skeleton } from '@/components/ui/skeleton'
import { usePerson } from '@/lib/hooks/useMembers'

interface MemberSidebarProps {
  personId: string
  onClose: () => void
}

export function MemberSidebar({ personId, onClose }: MemberSidebarProps) {
  const t = useTranslations('tree')
  const { data: member, isLoading } = usePerson(personId)

  return (
    <div className="absolute top-4 left-4 z-20 w-64 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2">
        <span className="text-sm font-semibold text-gray-700">{t('details')}</span>
        <button onClick={onClose} className="text-gray-400 transition-colors hover:text-gray-600">
          <X className="h-4 w-4" />
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-3 p-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-12 w-12 shrink-0 rounded-full" />
            <div className="flex-1 space-y-1">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-3 w-20" />
            </div>
          </div>
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-3/4" />
        </div>
      ) : member ? (
        <div className="space-y-3 p-4">
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
            <p className="line-clamp-3 text-xs text-gray-500 italic">{member.notes}</p>
          )}

          <div className="flex gap-2 pt-1">
            <Link
              href={`/persons/${member.id}`}
              className="bg-primary-container text-primary-container-foreground hover:bg-primary-container-hover flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1.5 text-xs transition-colors"
            >
              <Users className="h-3 w-3" />
              {t('view_profile')}
            </Link>
            <Link
              href={`/persons/${member.id}/edit`}
              className="flex flex-1 items-center justify-center gap-1 rounded-md border border-gray-200 px-2 py-1.5 text-xs text-gray-600 transition-colors hover:bg-gray-50"
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
