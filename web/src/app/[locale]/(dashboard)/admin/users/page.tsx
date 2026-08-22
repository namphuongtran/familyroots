'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { PendingUsersList } from '@/components/admin/PendingUsersList'
import { RoleSelector } from '@/components/admin/RoleSelector'
import { useClanUserMutations, useClanUsers } from '@/lib/hooks/useAdmin'
import type { ClanRole } from '@/lib/types'

export default function AdminUsersPage() {
  const t = useTranslations('admin')
  const { data, isLoading } = useClanUsers()
  const { approve, reject, changeRole } = useClanUserMutations()

  const pending = data?.pending ?? []
  const approved = data?.approved ?? []

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-foreground font-serif text-2xl">{t('users_title')}</h1>

      <section className="border-border bg-card rounded-2xl border p-5 shadow-xs">
        <h2 className="text-muted-foreground mb-3 text-sm font-semibold tracking-wide uppercase">
          {t('pending_approval')}
        </h2>
        <PendingUsersList
          users={pending.map((u) => ({
            id: u.user_id,
            label: u.user_id,
            created_at: u.created_at,
            role: u.role,
          }))}
          isLoading={isLoading}
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
              <p className="text-foreground text-sm font-medium">{user.user_id}</p>
              <p className="text-muted-foreground text-xs">
                {user.person_id ? `Person: ${user.person_id}` : 'No linked person'}
              </p>
            </div>
            <RoleSelector
              value={user.role}
              onChange={(role: ClanRole) => changeRole.mutate({ userId: user.user_id, role })}
            />
          </div>
        ))}
      </section>
    </div>
  )
}
