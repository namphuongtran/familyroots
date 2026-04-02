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
    <div className="space-y-6 max-w-2xl">
      <h1 className="font-serif text-2xl text-gray-800">{t('users_title')}</h1>

      <section className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          {t('pending_approval')}
        </h2>
        <PendingUsersList
          users={pending.map((u) => ({
            id: u.user_id,
            full_name: u.user_id,
            email: u.user_id,
            created_at: u.created_at,
          }))}
          isLoading={isLoading}
          onApprove={(id) => approve.mutate(id)}
          onReject={(id) => reject.mutate(id)}
        />
      </section>

      <section className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          {t('all_members')}
        </h2>
        {approved.map((user) => (
          <div key={user.id} className="flex items-center justify-between py-2 border-b last:border-0 border-gray-50">
            <div>
              <p className="text-sm font-medium text-gray-700">{user.user_id}</p>
              <p className="text-xs text-gray-400">{user.person_id ?? '-'}</p>
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
