import { getTranslations } from 'next-intl/server'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import { getPerson, PersonProfile } from '@/features/persons'
import { getServerAuthContext } from '@/lib/server/auth-context'
import { getServerRequestContext } from '@/shared/http/context.server'
import { ApiError } from '@/shared/http/errors'

/**
 * Spec §7.6, "Hồ sơ một người". A Server Component: `getPerson`
 * (`@/features/persons`, the persons repository repository) runs here directly rather
 * than through `usePerson` — nothing on this screen needs to refetch after a
 * mutation (create/edit is the persons form), so there is no reason to pay for a client
 * bundle and a loading flash a plain `await` avoids.
 *
 * **404 is answered inline, not via `notFound()`.** Spec §7.6 wants
 * `Không tìm thấy người này trong dòng họ {clan_name}.`, which needs the
 * active clan's name — `not-found.tsx` cannot read this segment's own
 * `params` in the App Router, so branching here and rendering the same
 * "not found" content directly (still a 200) is what lets the message name
 * the clan at all. Every other error rethrows, for `error.tsx` to catch
 * (`T-17`'s retry).
 */
export default async function MemberDetailPage({
  params,
}: {
  params: Promise<{ id: string; locale: string }>
}) {
  const { id } = await params
  const t = await getTranslations('member')
  const [authContext, context] = await Promise.all([
    getServerAuthContext(),
    getServerRequestContext(),
  ])
  const canEdit =
    authContext?.currentClanRole === 'editor' || authContext?.currentClanRole === 'admin'
  const isAdmin = authContext?.currentClanRole === 'admin'
  const clanName = authContext?.clanMemberships.find(
    (membership) => membership.clan_id === authContext.currentClanId,
  )?.clan_name

  let person
  try {
    person = await getPerson(id, {}, { context })
  } catch (error) {
    if (error instanceof ApiError && error.code === 'person_not_found') {
      return (
        <div className="mx-auto max-w-2xl space-y-4 text-center">
          <p className="text-foreground text-sm font-medium">{t('not_found_title')}</p>
          <p className="text-muted-foreground text-sm">
            {clanName ? t('not_found_detail', { clanName }) : t('not_found_generic')}
          </p>
          <Link href=".." className="text-primary font-medium hover:underline">
            {t('back_to_list')}
          </Link>
        </div>
      )
    }
    throw error
  }

  return (
    <div className="space-y-4">
      <div className="mx-auto flex max-w-2xl items-center gap-2">
        <Link href=".." className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <h1 className="text-foreground font-serif text-xl">{t('profile_title')}</h1>
      </div>

      <PersonProfile person={person} canEdit={canEdit} isAdmin={isAdmin} />
    </div>
  )
}
