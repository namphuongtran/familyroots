'use client'

import { useTranslations } from 'next-intl'
import { MemberAvatar } from './MemberAvatar'
import { Skeleton } from '@/components/ui/skeleton'
import { formatLifespan, formatDate } from '@/lib/utils/date'
import { usePerson, usePersonMarriages, usePersonParentChild } from '@/lib/hooks/useMembers'
import { getMarriageStatusLabel, getParentChildTypeLabel } from '@/lib/utils/kinship'

export function MemberDetailClient({ personId }: { personId: string }) {
  const t = useTranslations('member')
  const { data: member, isLoading } = usePerson(personId)
  const { data: marriages } = usePersonMarriages(personId)
  const { data: parentChildRels } = usePersonParentChild(personId)

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-4">
          <Skeleton className="h-16 w-16 rounded-full shrink-0" />
          <div className="space-y-2">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-4 w-28" />
          </div>
        </div>
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    )
  }

  if (!member) return <p className="text-sm text-gray-400">{t('not_found')}</p>

  const isDeceased = !!member.death_date

  return (
    <div className="space-y-6">
      {/* Header card */}
      <div className="bg-white rounded-2xl p-5 border border-gray-100 shadow-sm flex items-start gap-4">
        <MemberAvatar
          avatarUrl={member.avatar_url}
          fullName={member.full_name}
          gender={member.gender}
          size="lg"
          isDeceased={isDeceased}
        />
        <div>
          <h2 className="font-serif text-xl text-gray-800">{member.full_name}</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            {formatLifespan(member.birth_date, member.death_date, member.birth_date_approx)}
          </p>
          {member.generation && (
            <span className="inline-block mt-1 text-xs bg-amber-100 text-amber-700 rounded px-2 py-0.5">
              {t('generation_label', { gen: member.generation })}
            </span>
          )}
        </div>
      </div>

      {/* Details */}
      <div className="bg-white rounded-2xl p-5 border border-gray-100 shadow-sm space-y-3">
        <h3 className="text-sm font-semibold text-gray-600">{t('details')}</h3>
        {member.birth_place && (
          <Detail label={t('birth_place')} value={member.birth_place} />
        )}
        {member.death_place && (
          <Detail label={t('death_place')} value={member.death_place} />
        )}
        {member.notes && (
          <Detail label={t('notes')} value={member.notes} />
        )}
      </div>

      {/* Marriages */}
      {marriages && marriages.length > 0 && (
        <div className="bg-white rounded-2xl p-5 border border-gray-100 shadow-sm space-y-3">
          <h3 className="text-sm font-semibold text-gray-600">{t('marriages')}</h3>
          <ul className="space-y-2">
            {marriages.map(m => (
              <li key={m.id} className="flex items-center justify-between text-sm">
                <span className="text-gray-500">{getMarriageStatusLabel(m.status)}</span>
                <span className="font-medium text-gray-700">
                  {m.person1_id === personId ? m.person2_id : m.person1_id}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Parent-Child */}
      {parentChildRels && parentChildRels.length > 0 && (
        <div className="bg-white rounded-2xl p-5 border border-gray-100 shadow-sm space-y-3">
          <h3 className="text-sm font-semibold text-gray-600">{t('relationships')}</h3>
          <ul className="space-y-2">
            {parentChildRels.map(rel => (
              <li key={rel.id} className="flex items-center justify-between text-sm">
                <span className="text-gray-500">
                  {rel.parent_id === personId ? t('child') : t('parent')} ({getParentChildTypeLabel(rel.relationship_type)})
                </span>
                <span className="font-medium text-gray-700">
                  {rel.parent_id === personId ? rel.child_id : rel.parent_id}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className="text-sm text-gray-800">{value}</p>
    </div>
  )
}
