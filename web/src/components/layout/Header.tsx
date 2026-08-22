'use client'

import { useTransition } from 'react'
import { useTranslations } from 'next-intl'
import { LogOut, User, ChevronDown } from 'lucide-react'
import { LocaleSwitcher } from './LocaleSwitcher'
import { useAuth } from '@/lib/hooks/useAuth'
import { cn } from '@/lib/utils/cn'
import { useState } from 'react'

interface HeaderProps {
  title?: string
}

export function Header({ title }: HeaderProps) {
  const t = useTranslations()
  const { user, currentClanId, clanMemberships, needsClanSelection, signOut, selectClan } =
    useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const [isSwitching, startTransition] = useTransition()

  return (
    <header className="border-cream-200 flex h-16 shrink-0 items-center justify-between border-b bg-white px-6">
      <h1 className="text-foreground truncate font-serif text-lg font-semibold">{title ?? ''}</h1>

      <div className="flex items-center gap-3">
        {clanMemberships.length > 0 && (
          <label className="text-muted-foreground hidden items-center gap-2 text-sm md:flex">
            <span className="text-muted-foreground text-xs tracking-wide uppercase">Clan</span>
            <select
              value={currentClanId ?? ''}
              disabled={isSwitching || clanMemberships.length === 1}
              onChange={(event) => {
                const nextClanId = event.target.value
                if (!nextClanId || nextClanId === currentClanId) {
                  return
                }

                startTransition(async () => {
                  await selectClan(nextClanId)
                  setMenuOpen(false)
                })
              }}
              className="border-input bg-card text-foreground rounded-md border px-2 py-1 text-sm disabled:cursor-default disabled:opacity-70"
            >
              {needsClanSelection && <option value="">Select clan</option>}
              {clanMemberships.map((membership) => (
                <option key={membership.clan_id} value={membership.clan_id}>
                  {membership.clan_name}
                </option>
              ))}
            </select>
          </label>
        )}

        <LocaleSwitcher />

        {/* User menu */}
        <div className="relative">
          <button
            onClick={() => setMenuOpen((o) => !o)}
            className="hover:bg-cream-100 text-foreground flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm"
          >
            <User className="h-4 w-4" />
            <span className="hidden max-w-[120px] truncate sm:block">{user?.full_name}</span>
            <ChevronDown className="h-3 w-3 opacity-60" />
          </button>

          {menuOpen && (
            <>
              {/* Backdrop */}
              <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
              <div
                className={cn(
                  'border-cream-200 absolute top-full right-0 z-20 mt-1 w-48 rounded-lg border bg-white shadow-lg',
                  'py-1',
                )}
              >
                <div className="border-cream-100 border-b px-3 py-2">
                  <p className="text-foreground truncate text-xs font-medium">{user?.full_name}</p>
                  <p className="text-muted-foreground truncate text-xs">{user?.email}</p>
                </div>
                {clanMemberships.length > 1 && (
                  <div className="border-cream-100 border-b px-3 py-2">
                    <p className="text-muted-foreground mb-1 text-[11px] tracking-wide uppercase">
                      Clan
                    </p>
                    <select
                      value={currentClanId ?? ''}
                      disabled={isSwitching}
                      onChange={(event) => {
                        const nextClanId = event.target.value
                        if (!nextClanId || nextClanId === currentClanId) {
                          return
                        }

                        startTransition(async () => {
                          await selectClan(nextClanId)
                          setMenuOpen(false)
                        })
                      }}
                      className="border-input bg-card text-foreground w-full rounded-md border px-2 py-1 text-sm"
                    >
                      {clanMemberships.map((membership) => (
                        <option key={membership.clan_id} value={membership.clan_id}>
                          {membership.clan_name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <button
                  onClick={signOut}
                  className="text-destructive hover:bg-destructive/10 flex w-full items-center gap-2 px-3 py-2 text-sm"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  {t('auth.logout')}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
