'use client'

/**
 * Spec §7.2c (`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:955-961`), for
 * `403 clan_suspended` (`docs/contracts/error-codes.md`, "Clan context & permissions"). Reached
 * with `?clanId=&clanName=` from `select-clan/page.tsx`, the one real, already-wired call site
 * in this codebase that can surface this code today: `useAuth().selectClan` →
 * `authProfileRepository.selectClan` → `POST /me/clans/{clan_id}/select` via the legacy axios
 * client (`src/lib/api/axios.ts`), which does not normalize its error into `ApiError` — the
 * envelope's `error.code` sits at `AxiosError.response.data.error.code`. `select-clan/page.tsx`
 * reads it there rather than importing anything from the frozen axios tree.
 *
 * The `clanName` query param is the name from the membership row the user just clicked in
 * `select-clan/page.tsx` — sent through rather than re-fetched, since the clan itself may now be
 * failing every lookup. `clanId` lets this screen tell "another approved clan besides this one"
 * apart from "this was the only one", via `useAuth().clanMemberships` (approved memberships;
 * whether a suspended clan still appears in that list is not verified against backend source —
 * `docs/contracts/frontend-integration-guide.md` §1.2 documents no filter on `clans.is_active` —
 * but the "some other entry exists" check below is correct either way).
 *
 * Spec §2.1's `warning-container`/`on-warning-container` tokens do not exist in
 * `globals.css`'s `@theme` (only `primary`, `heritage`, and the seventeen shadcn-style names do
 * — see `web/CLAUDE.md`, "Dependency rules" is silent on this, `.claude/rules/tailwind.md` §2
 * is not). Using the class anyway would be a dead class, which the seed's end state forbids.
 * `accent`/`accent-foreground` (`#fef3c7`/`#92400e`) are this codebase's existing stand-in for a
 * warning tone — `globals.css`'s own dark-theme comment calls them "the dark warning pair" — and
 * the pair is already gated in `contrast.test.ts`, so this screen uses `bg-accent` /
 * `text-accent-foreground` rather than inventing a new token.
 */
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { ShieldAlert } from 'lucide-react'
import { useAuth } from '@/lib/hooks/useAuth'

export function ClanSuspendedScreen() {
  const t = useTranslations('auth')
  const locale = useLocale()
  const searchParams = useSearchParams()
  const clanId = searchParams.get('clanId') ?? undefined
  const clanName = searchParams.get('clanName') || undefined
  const { clanMemberships, signOut } = useAuth()

  const hasOtherClans = clanMemberships.some((membership) => membership.clan_id !== clanId)

  return (
    <div className="flex min-h-screen items-center justify-center bg-accent px-4 py-12">
      <div className="w-full max-w-md space-y-6 text-center">
        <ShieldAlert className="mx-auto h-12 w-12 text-accent-foreground" aria-hidden="true" />

        <div className="space-y-2">
          <h1 className="font-serif text-2xl text-accent-foreground">
            {clanName
              ? t('clan_suspended_heading_with_name', { clanName })
              : t('clan_suspended_heading_no_name')}
          </h1>
          <p className="text-sm text-accent-foreground">{t('clan_suspended_body')}</p>
        </div>

        {/* T-17: never a dead end. The contextual action is "switch clan" when another
            approved clan exists, but sign-out is always offered too, not swapped out for it —
            a suspended-clan user should never be one missing "other clans" list away from
            having no button at all. */}
        <div className="flex flex-col items-center gap-3">
          {hasOtherClans && (
            <Link
              href={`/${locale}/select-clan`}
              className="w-full max-w-xs rounded-full bg-primary px-4 py-2.5 text-center text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover focus:outline-hidden focus:ring-2 focus:ring-ring focus:ring-offset-2"
            >
              {t('clan_suspended_switch_button')}
            </Link>
          )}

          <button
            type="button"
            onClick={() => void signOut()}
            className={
              hasOtherClans
                ? 'text-sm text-accent-foreground/80 hover:text-accent-foreground'
                : 'w-full max-w-xs rounded-full bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover focus:outline-hidden focus:ring-2 focus:ring-ring focus:ring-offset-2'
            }
          >
            {t('logout')}
          </button>
        </div>
      </div>
    </div>
  )
}
