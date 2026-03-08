'use client'

import { useTranslations } from 'next-intl'
import { MemberAvatar } from './MemberAvatar'
import { Skeleton } from '@/components/ui/skeleton'
import { formatLifespan, formatDate } from '@/lib/utils/date'
import { useMember, useMemberRelationships } from '@/lib/hooks/useMembers'
import { getRelationLabel } from '@/lib/utils/kinship'

export function MemberDetailClient({ memberId }: { memberId: string }) {
  const t = useTranslations('member')
  const { data: member, isLoading } = useMember(memberId)
  const { data: rels } = useMemberRelationships(memberId)

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

      {/* Relationships */}
      {rels && rels.length > 0 && (
        <div className="bg-white rounded-2xl p-5 border border-gray-100 shadow-sm space-y-3">
          <h3 className="text-sm font-semibold text-gray-600">{t('relationships')}</h3>
          <ul className="space-y-2">
            {rels.map(rel => (
              <li key={rel.id} className="flex items-center justify-between text-sm">
                <span className="text-gray-500">{getRelationLabel(rel.relation_type, rel.relation_subtype)}</span>
                <span className="font-medium text-gray-700">{rel.related_id}</span>
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
