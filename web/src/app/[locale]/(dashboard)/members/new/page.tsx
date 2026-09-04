'use client'

import { useRouter, useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import { PersonForm, usePersonsRequestContext } from '@/features/persons'
import { useCapabilities } from '@/lib/hooks/useCapabilities'
import { Skeleton } from '@/components/ui/skeleton'

/**
 * Spec §7.7, create. Replaces the legacy `MemberForm` this route
 * used through the persons list screens — same migration shape as the list/detail screens:
 * this route no longer imports anything under `src/components/members/` or
 * `src/lib/hooks/useMembers`. `MemberForm.tsx` itself is left in place;
 * deleting it is the legacy-component deletion's.
 */
export default function NewMemberPage() {
  const t = useTranslations('member')
  const router = useRouter()
  const { locale } = useParams<{ locale: string }>()
  const { canEditPersons } = useCapabilities()
  const { context, ready } = usePersonsRequestContext()

  if (!canEditPersons) {
    return <p className="text-muted-foreground text-sm">{t('no_permission_edit')}</p>
  }

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <div className="flex items-center gap-2">
        <Link href={`/${locale}/members`} className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <h1 className="text-foreground font-serif text-xl">{t('new_title')}</h1>
      </div>

      {ready ? (
        <PersonForm
          mode="create"
          context={context}
          onSuccess={(person) => router.push(`/${locale}/members/${person.id}`)}
          onCancel={() => router.back()}
        />
      ) : (
        <div className="space-y-3">
          {Array.from({ length: 5 }, (_, index) => (
            <Skeleton key={index} className="h-10 w-full rounded-lg" />
          ))}
        </div>
      )}
    </div>
  )
}
