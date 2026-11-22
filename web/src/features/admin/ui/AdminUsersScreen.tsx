'use client'

import { useTranslations } from 'next-intl'
import type { ClanRole } from '@/domain/capability/capability'
import { useClientRequestContext } from '@/shared/http/context.client'
import { useClanUserMutations, useClanUsers } from '../hooks/use-admin-queries'
import { PendingUsersList } from './PendingUsersList'
import { RoleSelector } from './RoleSelector'

/**
 * The admin users page: the pending queue, then every approved account with its role. An account
 * is named by its display name, then (pending only, ADR-039) its email, then its id.
 */
export function AdminUsersScreen() {
  const t = useTranslations('admin')
  const request = useClientRequestContext()
  const options = { context: request.context, refreshAuth: request.refreshAuth }
  const users = useClanUsers({ ...options, enabled: request.ready })
  const { approve, reject, changeRole } = useClanUserMutations(options)

  const pending = users.data?.pending ?? []
  const approved = users.data?.approved ?? []

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-foreground font-serif text-2xl">{t('users_title')}</h1>

      <section className="border-border bg-card rounded-2xl border p-5 shadow-xs">
        <h2 className="text-muted-foreground mb-3 text-sm font-semibold tracking-wide uppercase">
          {t('pending_approval')}
        </h2>
        <PendingUsersList
          users={pending.map((u) => ({
            id: u.userId,
            label: u.displayName ?? u.email ?? u.userId,
            created_at: u.createdAt,
            role: u.role ?? undefined,
          }))}
          isLoading={!request.ready || users.isPending}
          onApprove={(id) => approve.mutate(id)}
          onReject={(id) => reject.mutate(id)}
        />
      </section>

      <section className="border-border bg-card rounded-2xl border p-5 shadow-xs">
        <h2 className="text-muted-foreground mb-3 text-sm font-semibold tracking-wide uppercase">
          {t('all_members')}
        </h2>
        {approved.map((user) => (
          <div
            key={user.id}
            className="border-border flex items-center justify-between border-b py-2 last:border-0"
          >
            <div>
              <p className="text-foreground text-sm font-medium">
                {user.displayName ?? user.userId}
              </p>
              <p className="text-muted-foreground text-xs">
                {user.personId ? t('linked_person', { id: user.personId }) : t('no_linked_person')}
              </p>
            </div>
            {user.role && (
              <RoleSelector
                value={user.role}
                onChange={(role: ClanRole) => changeRole.mutate({ userId: user.userId, role })}
              />
            )}
          </div>
        ))}
      </section>
    </div>
  )
}
