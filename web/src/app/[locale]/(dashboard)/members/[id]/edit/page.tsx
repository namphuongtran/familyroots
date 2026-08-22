'use client'

import { useRouter, useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import {
  PersonForm,
  PersonsErrorState,
  usePerson,
  usePersonsRequestContext,
} from '@/features/persons'
import { useCapabilities } from '@/lib/hooks/useCapabilities'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/shared/http/errors'

/**
 * Spec §7.7, edit (S-032). Replaces the legacy `MemberForm` +
 * `useMembers().usePerson` this route used through S-031, same as `new/page.tsx`.
 * `usePerson` here is S-030's own hook (`@/features/persons`), not the
 * legacy `src/lib/hooks/useMembers.ts` one the two share a name with.
 */
export default function EditMemberPage() {
  const t = useTranslations('member')
  const router = useRouter()
  const { id, locale } = useParams<{ id: string; locale: string }>()
  const { canEditPersons } = useCapabilities()
  const { context, ready } = usePersonsRequestContext()
  const { data: person, isPending, error, refetch } = usePerson(id, {}, { context, enabled: ready })

  if (!canEditPersons) {
    return <p className="text-muted-foreground text-sm">{t('no_permission_edit')}</p>
  }

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <div className="flex items-center gap-2">
        <Link href=".." className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <h1 className="text-foreground font-serif text-xl">{t('edit_title')}</h1>
      </div>

      {!ready || isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }, (_, index) => (
            <Skeleton key={index} className="h-10 w-full rounded-lg" />
          ))}
        </div>
      ) : person ? (
        <PersonForm
          mode="edit"
          person={person}
          context={context}
          onSuccess={() => router.push(`/${locale}/members/${id}`)}
          onCancel={() => router.back()}
        />
      ) : (
        <PersonsErrorState
          title={t('error_title')}
          message={error instanceof ApiError ? error.message : null}
          onRetry={() => refetch()}
        />
      )}
    </div>
  )
}
