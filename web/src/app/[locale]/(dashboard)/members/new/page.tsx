'use client'

import { useRouter, useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import { MemberForm } from '@/components/members/MemberForm'

export default function NewMemberPage() {
  const t = useTranslations('member')
  const router = useRouter()
  const { locale } = useParams<{ locale: string }>()

  return (
    <div className="max-w-xl mx-auto space-y-4">
      <div className="flex items-center gap-2">
        <Link href={`/${locale}/members`} className="text-gray-400 hover:text-gray-600">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <h1 className="font-serif text-xl text-gray-800">{t('new_title')}</h1>
      </div>

      <div className="bg-white rounded-2xl p-6 border border-gray-100 shadow-sm">
        <MemberForm
          onSuccess={id => router.push(`/${locale}/members/${id}`)}
          onCancel={() => router.back()}
        />
      </div>
    </div>
  )
}
