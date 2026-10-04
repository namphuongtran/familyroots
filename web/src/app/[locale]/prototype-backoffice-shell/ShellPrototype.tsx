'use client'

// PROTOTYPE — throwaway, for "How should the backoffice shell behave at 320 px and 200 percent
// text?" (issue #162). Never merge to main.
//
// Plan: four shells around the real backoffice dashboard content, switchable via `?variant=`,
// on a throwaway route outside the role gate so it can be viewed without a Supabase session.
//   now — today's layout, `fixed w-60` + `ml-60`, kept as the control
//   A   — drawer below lg (spec § 6: "< 1024 drawer nav")
//   B   — icon-only rail below lg
//   C   — rail stacks above the content below lg, page scrolls
// Everything is in rem on purpose, so the "200% text" toggle doubles it the way a 32px root does.

import { useState, type ReactNode } from 'react'
import Link from 'next/link'
import { usePathname, useSearchParams } from 'next/navigation'
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
import { cn } from '@/lib/utils/cn'
import { PrototypeSwitcher } from '@/components/prototype/PrototypeSwitcher'

const VARIANTS = [
  { key: 'now', name: 'Today: fixed w-60 + ml-60' },
  { key: 'A', name: 'Drawer below 1024' },
  { key: 'B', name: 'Icon rail below 1024' },
  { key: 'C', name: 'Stacked above content' },
] as const

const NAV_ITEMS = [
  { href: 'dashboard', labelKey: 'nav_dashboard', icon: LayoutDashboard },
  { href: 'members', labelKey: 'nav_members', icon: Users },
  { href: 'clans', labelKey: 'nav_clans', icon: Building2 },
  { href: 'tree', labelKey: 'nav_tree', icon: TreeDeciduous },
] as const

export function ShellPrototype({ locale, children }: { locale: string; children: ReactNode }) {
  const variant = useSearchParams().get('variant') ?? 'now'
  return (
    <>
      {variant === 'now' && <VariantNow locale={locale}>{children}</VariantNow>}
      {variant === 'A' && <VariantA locale={locale}>{children}</VariantA>}
      {variant === 'B' && <VariantB locale={locale}>{children}</VariantB>}
      {variant === 'C' && <VariantC locale={locale}>{children}</VariantC>}
      <PrototypeSwitcher variants={VARIANTS} />
    </>
  )
}

// ── shared bits (header-level sharing only; each variant owns its layout) ──────────────────────

function Brand({ wordmark = true }: { wordmark?: boolean }) {
  const t = useTranslations('Backoffice')
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <span className="text-primary font-serif text-lg font-bold">FR</span>
      {wordmark && (
        <div className="min-w-0 leading-tight">
          <p className="text-foreground text-xs">{t('rail_label')}</p>
          {/* Measured: one unbreakable word overflowed the top bar by 5px and pushed the drawer's
              close button off-screen. `<wbr>` is the login/register precedent. */}
          <p className="text-xs font-semibold">
            Family<wbr />
            Roots
          </p>
        </div>
      )}
    </div>
  )
}

function useActive(locale: string) {
  const pathname = usePathname()
  // The prototype route is not a backoffice route, so pretend the dashboard is active.
  return (href: string) =>
    pathname.startsWith(`/${locale}/backoffice/${href}`) ||
    (href === 'dashboard' && pathname.includes('prototype-backoffice-shell'))
}

function NavColumn({ locale, onNavigate }: { locale: string; onNavigate?: () => void }) {
  const t = useTranslations('Backoffice')
  const isActive = useActive(locale)
  return (
    <nav className="space-y-1">
      {NAV_ITEMS.map(({ href, labelKey, icon: Icon }) => {
        const active = isActive(href)
        return (
          <Link
            key={href}
            href={`/${locale}/backoffice/${href}`}
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
  )
}

function Logout({ iconOnly = false }: { iconOnly?: boolean }) {
  const tAuth = useTranslations('auth')
  return (
    <button
      // Stubbed: the prototype does not touch the session.
      onClick={() => alert('PROTOTYPE: sign-out is stubbed')}
      aria-label={iconOnly ? tAuth('logout') : undefined}
      className="text-muted-foreground hover:bg-card hover:text-foreground flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors"
    >
      <LogOut className="h-4 w-4 shrink-0" />
      {!iconOnly && tAuth('logout')}
    </button>
  )
}

// ── now: the control, today's markup ───────────────────────────────────────────────────────────

function VariantNow({ locale, children }: { locale: string; children: ReactNode }) {
  return (
    <div className="bg-background flex min-h-screen">
      <aside className="bg-muted text-foreground fixed top-0 left-0 flex h-screen w-60 shrink-0 flex-col">
        <div className="mb-2 flex h-16 items-center px-5">
          <Brand />
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-4">
          <NavColumn locale={locale} />
        </div>
        <div className="mt-2 px-3 py-4">
          <Logout />
        </div>
      </aside>
      <main className="bg-background ml-60 min-h-screen flex-1 overflow-y-auto">{children}</main>
    </div>
  )
}

// ── A: drawer below lg, static rail at lg+ ─────────────────────────────────────────────────────

function VariantA({ locale, children }: { locale: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="bg-background min-h-screen lg:flex">
      {/* Below lg: a top bar with the menu button. The rail lives in a modal drawer. */}
      <header className="bg-muted text-foreground sticky top-0 z-30 flex items-center gap-2 px-2 py-1 lg:hidden">
        <Dialog.Root open={open} onOpenChange={setOpen}>
          <Dialog.Trigger asChild>
            <button
              aria-label="Mở menu điều hướng"
              className="hover:bg-card flex min-h-11 min-w-11 items-center justify-center rounded-full"
            >
              <Menu className="h-5 w-5" />
            </button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40 lg:hidden" />
            <Dialog.Content className="bg-muted text-foreground fixed inset-y-0 left-0 z-50 flex w-[min(85vw,16.5rem)] flex-col overflow-y-auto lg:hidden">
              <Dialog.Title className="sr-only">Điều hướng quản trị</Dialog.Title>
              <div className="flex items-start justify-between gap-2 px-4 py-3">
                <Brand />
                <Dialog.Close
                  aria-label="Đóng"
                  className="hover:bg-card flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full"
                >
                  <X className="h-5 w-5" />
                </Dialog.Close>
              </div>
              <div className="flex-1 px-3 py-2">
                <NavColumn locale={locale} onNavigate={() => setOpen(false)} />
              </div>
              <div className="px-3 py-4">
                <Logout />
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
        <Brand />
      </header>

      {/* lg+: the rail is a sibling in the flex row, so main's width comes from flex, not ml-*. */}
      <aside className="bg-muted text-foreground sticky top-0 hidden h-screen w-[16.5rem] shrink-0 flex-col lg:flex">
        <div className="mb-2 flex h-16 items-center px-5">
          <Brand />
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-4">
          <NavColumn locale={locale} />
        </div>
        <div className="mt-2 px-3 py-4">
          <Logout />
        </div>
      </aside>

      <main className="bg-background min-w-0 flex-1">{children}</main>
    </div>
  )
}

// ── B: icon-only rail below lg, full rail at lg+ ───────────────────────────────────────────────

function VariantB({ locale, children }: { locale: string; children: ReactNode }) {
  const t = useTranslations('Backoffice')
  const isActive = useActive(locale)
  return (
    <div className="bg-background flex min-h-screen">
      <aside className="bg-muted text-foreground sticky top-0 flex h-screen w-[4.5rem] shrink-0 flex-col items-stretch lg:w-[16.5rem]">
        <div className="mb-2 flex h-16 items-center justify-center lg:justify-start lg:px-5">
          <span className="lg:hidden">
            <Brand wordmark={false} />
          </span>
          <span className="hidden lg:block">
            <Brand />
          </span>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-2 py-4 lg:px-3">
          {NAV_ITEMS.map(({ href, labelKey, icon: Icon }) => {
            const active = isActive(href)
            return (
              <Link
                key={href}
                href={`/${locale}/backoffice/${href}`}
                title={t(labelKey)}
                className={cn(
                  'flex min-h-11 items-center justify-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors lg:justify-start',
                  active
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-card hover:text-foreground',
                )}
              >
                <Icon className="h-5 w-5 shrink-0 lg:h-4 lg:w-4" />
                {/* Label is announced but not drawn below lg. */}
                <span className="sr-only lg:not-sr-only">{t(labelKey)}</span>
              </Link>
            )
          })}
        </nav>
        <div className="mt-2 px-2 py-4 lg:px-3">
          <span className="lg:hidden">
            <Logout iconOnly />
          </span>
          <span className="hidden lg:block">
            <Logout />
          </span>
        </div>
      </aside>
      <main className="bg-background min-w-0 flex-1">{children}</main>
    </div>
  )
}

// ── C: rail stacks above the content below lg, page scrolls ────────────────────────────────────

function VariantC({ locale, children }: { locale: string; children: ReactNode }) {
  const t = useTranslations('Backoffice')
  const isActive = useActive(locale)
  return (
    <div className="bg-background min-h-screen lg:flex">
      <aside className="bg-muted text-foreground flex flex-col lg:sticky lg:top-0 lg:h-screen lg:w-[16.5rem] lg:shrink-0">
        <div className="flex items-center justify-between gap-2 px-4 py-3 lg:mb-2 lg:h-16 lg:px-5 lg:py-0">
          <Brand />
        </div>
        {/* Below lg the links wrap as a row of chips; at lg+ they are the usual column. */}
        <nav className="flex flex-wrap gap-2 px-3 pb-3 lg:flex-1 lg:flex-col lg:flex-nowrap lg:gap-1 lg:overflow-y-auto lg:py-4">
          {NAV_ITEMS.map(({ href, labelKey, icon: Icon }) => {
            const active = isActive(href)
            return (
              <Link
                key={href}
                href={`/${locale}/backoffice/${href}`}
                className={cn(
                  'flex items-center gap-2 rounded-full px-3 py-2 text-sm transition-colors lg:gap-3 lg:rounded-lg',
                  active
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-card text-muted-foreground hover:text-foreground lg:hover:bg-card lg:bg-transparent',
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {t(labelKey)}
              </Link>
            )
          })}
        </nav>
        <div className="px-3 pb-3 lg:mt-2 lg:py-4">
          <Logout />
        </div>
      </aside>
      <main className="bg-background min-w-0 flex-1">{children}</main>
    </div>
  )
}
