'use client'

import { useRouter, useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import { MemberForm } from '@/components/members/MemberForm'
import { usePerson } from '@/lib/hooks/useMembers'
import { Skeleton } from '@/components/ui/skeleton'

export default function EditMemberPage() {
  const t = useTranslations('member')
  const router = useRouter()
  const { id, locale } = useParams<{ id: string; locale: string }>()
  const { data: member, isLoading } = usePerson(id)

  return (
    <div className="max-w-xl mx-auto space-y-4">
      <div className="flex items-center gap-2">
        <Link href={`..`} className="text-gray-400 hover:text-gray-600">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <h1 className="font-serif text-xl text-gray-800">{t('edit_title')}</h1>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 w-full rounded-md" />)}
        </div>
      ) : (
        <div className="bg-white rounded-2xl p-6 border border-gray-100 shadow-sm">
          <MemberForm
            member={member}
            onSuccess={() => router.push(`/${locale}/members/${id}`)}
            onCancel={() => router.back()}
          />
        </div>
      )}
    </div>
  )
}
