'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import * as Dialog from '@radix-ui/react-dialog'
import {
  Users,
  TreeDeciduous,
  Building2,
  LayoutDashboard,
  ChevronRight,
  LogOut,
  Menu,
  X,
} from 'lucide-react'
import { useAuthActions } from '@/features/auth'
import { cn } from '@/lib/utils/cn'

/** The menu and close buttons: icon-only, so each carries an `aria-label`. T-03's 44×44 px at
 * the default font size, and it grows with text. */
const ICON_BUTTON =
  'hover:bg-card flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full'

const NAV_ITEMS = [
  { href: 'dashboard', labelKey: 'nav_dashboard', icon: LayoutDashboard },
  { href: 'members', labelKey: 'nav_members', icon: Users },
  { href: 'clans', labelKey: 'nav_clans', icon: Building2 },
  { href: 'tree', labelKey: 'nav_tree', icon: TreeDeciduous },
] as const

function Brand() {
  const t = useTranslations('Backoffice')

  return (
    // `min-w-0` here and on the text column lets the brand shrink below its longest word. The
    // #162 prototype needed it with the `<wbr>`: without both, the wordmark ran 5px past the top
    // bar and pushed the drawer's close button off a 320px screen at 200% text. Since the drawer
    // header wraps, removing it alone changes no reading in the e2e cases (measured 2026-10-04);
    // removing the `<wbr>` still overflows the top bar.
    <div className="flex min-w-0 items-center gap-2.5">
      {/*
        ADR-046 ("The backoffice aside stops being inverted and becomes a
        surface step") converted this aside from a hand-built bg-gray-950
        to the `muted` token, so every ink here is now a pair
        contrast.test.ts already runs against `muted` in both schemes. The
        mark used to take `primary-container` because `primary` measured
        only 2.68:1 on the old #030712 ground; on `muted` the order swaps:
        measured 2026-08-22, `primary` is 6.83:1 in light and 8.20:1 in
        dark, while `primary-container` drops to 1.20:1 and 1.50:1. See the
        ADR for the full table and the one-cause explanation (a token
        placed on a ground outside the token system fails in one theme or
        the other, because the ink moves and the ground cannot).
      */}
      <span className="text-primary font-serif text-lg font-bold">FR</span>
      <div className="min-w-0 leading-tight">
        <p className="text-foreground text-xs">{t('rail_label')}</p>
        {/* `<wbr />` is load-bearing — see the note on the login page (T-04). */}
        <p className="text-xs font-semibold">
          Family
          <wbr />
          Roots
        </p>
      </div>
    </div>
  )
}

/**
 * The rail's body: the four links and sign-out, written once. The rail at `lg` and up and the
 * drawer below it both render this, so the two cannot drift apart.
 *
 * It takes `onSignOut` rather than calling `useAuthActions()` itself, so the rail and the drawer
 * share one sign-out. Before #183 this mattered more: every legacy `useAuth()` consumer hydrated
 * the session on mount, so a body that called it added a hydration each time the drawer opened.
 * `useAuthActions` reads no session, so that cost is gone, but one call for both still holds.
 */
function RailBody({
  locale,
  onSignOut,
  onNavigate,
}: {
  locale: string
  onSignOut: () => void
  onNavigate?: () => void
}) {
  const t = useTranslations('Backoffice')
  // `auth.logout` rather than a new `Backoffice.*` key: the sentence already has one key,
  // real translations in all four locale files, and three other callers (`Header.tsx`,
  // `PendingApprovalScreen.tsx`, `ClanSuspendedScreen.tsx`). The logout-label fix.
  const tAuth = useTranslations('auth')
  const pathname = usePathname()

  return (
    <>
      {/* No `overflow-y-auto` here: the rail and the drawer each scroll as a whole. A nav that
          scrolled on its own hid two of the four links in the drawer at 200% text, with nothing
          on screen to say they were there. */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV_ITEMS.map(({ href, labelKey, icon: Icon }) => {
          const fullHref = `/${locale}/backoffice/${href}`
          const active = pathname.startsWith(fullHref)
          return (
            <Link
              key={href}
              href={fullHref}
              onClick={onNavigate}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                active
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-card hover:text-foreground',
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {t(labelKey)}
              {active && <ChevronRight className="ml-auto h-3 w-3 opacity-60" />}
            </Link>
          )
        })}
      </nav>

      <div className="mt-2 px-3 py-4">
        <button
          onClick={onSignOut}
          className="text-muted-foreground hover:bg-card hover:text-foreground flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors"
        >
          <LogOut className="h-4 w-4 shrink-0" />
          {tAuth('logout')}
        </button>
      </div>
    </>
  )
}

/**
 * The backoffice navigation, in both of its forms. Below `lg`, spec § 6's drawer nav: a top bar
 * with a menu button and the brand, and the rail in a modal drawer. At `lg` and up, the rail.
 *
 * The rail is an in-flow sibling of `main` in the layout's flex row (`sticky`, which stays in
 * flow, so it holds still while the page scrolls), so `main` takes the rest of the row
 * from `flex-1` rather than from a margin that matches the rail's width. A `fixed` rail paired
 * with `ml-*` is the #174 defect: at 320px and 200% text the margin alone was wider than the
 * screen and `main` collapsed to zero. `16.5rem` is spec § 6's 264px at the default font size,
 * and it stays in rem so it grows with text.
 *
 * The drawer is built on `@radix-ui/react-dialog`, which `StaleWriteDialog` set the pattern for.
 * It differs from that dialog in three ways, each on purpose:
 *
 * - **It closes on Escape and on a scrim tap.** That dialog refuses both because dismissing it
 *   loses a clan member's work. A navigation drawer has nothing to lose.
 * - **It owns its `open` state, behind a `Dialog.Trigger`.** That dialog's caller owns `open`
 *   because the caller knows whether a conflict exists. Nothing outside this component needs to
 *   know whether the drawer is open.
 * - **Its title is `sr-only`, it has no description, and its two buttons carry `aria-label`s.**
 *   That dialog shows a real heading and body text. A drawer of links has no sentence to show, and
 *   its buttons are icons with no text of their own to be named by.
 *
 * Neither the overlay nor the drawer is `lg:hidden`. A drawer left open across a resize to `lg`
 * stays visible and dismissable. Hiding it with CSS would leave Radix's focus trap and scroll lock
 * holding a page whose modal nobody can see.
 */
export function BackofficeSidebar({ locale }: { locale: string }) {
  const t = useTranslations('Backoffice')
  const tCommon = useTranslations('common')
  const { signOut } = useAuthActions()
  const [open, setOpen] = useState(false)
  const onSignOut = () => void signOut()

  return (
    <>
      {/* A nav bar the page scrolls under, so it takes the mandate's glass: 80% plus a 20px blur. */}
      <header className="bg-muted/80 text-foreground sticky top-0 z-30 flex items-center gap-2 px-2 py-1 backdrop-blur-[20px] lg:hidden">
        <Dialog.Root open={open} onOpenChange={setOpen}>
          <Dialog.Trigger aria-label={t('menu_open')} className={ICON_BUTTON}>
            <Menu className="h-5 w-5" />
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
            <Dialog.Content
              aria-describedby={undefined}
              className="bg-muted text-foreground fixed inset-y-0 left-0 z-50 flex w-[min(85vw,16.5rem)] flex-col overflow-y-auto"
            >
              <Dialog.Title className="sr-only">{t('menu_title')}</Dialog.Title>
              {/*
                `flex-wrap-reverse`: when the brand and the close button do not fit on one line,
                the close button wraps onto a line of its own *above* the brand (`ml-auto` keeps it
                at the right), and the brand gets the drawer's whole width. Measured at 320px and
                200% text with both on one line: the 88px button left the brand's text column 39px,
                so the words inked past it into the button's hit box, and English's unbreakable
                "Backoffice" would have reached the X itself.
              */}
              <div className="flex flex-wrap-reverse items-center justify-between gap-2 px-4 py-3">
                <Brand />
                <Dialog.Close aria-label={tCommon('close')} className={cn(ICON_BUTTON, 'ml-auto')}>
                  <X className="h-5 w-5" />
                </Dialog.Close>
              </div>
              <RailBody locale={locale} onSignOut={onSignOut} onNavigate={() => setOpen(false)} />
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
        <Brand />
      </header>

      <aside className="bg-muted text-foreground sticky top-0 hidden h-screen w-[16.5rem] shrink-0 flex-col overflow-y-auto lg:flex">
        <div className="mb-2 flex h-16 items-center px-5">
          <Brand />
        </div>
        <RailBody locale={locale} onSignOut={onSignOut} />
      </aside>
    </>
  )
}
