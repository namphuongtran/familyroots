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
      <h1 className="font-serif text-2xl text-gray-800">{t('users_title')}</h1>

      <section className="rounded-2xl border border-gray-100 bg-white p-5 shadow-xs">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-gray-500 uppercase">
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

      <section className="rounded-2xl border border-gray-100 bg-white p-5 shadow-xs">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-gray-500 uppercase">
          {t('all_members')}
        </h2>
        {approved.map((user) => (
          <div
            key={user.id}
            className="flex items-center justify-between border-b border-gray-50 py-2 last:border-0"
          >
            <div>
              <p className="text-sm font-medium text-gray-700">{user.user_id}</p>
              <p className="text-xs text-gray-400">
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
