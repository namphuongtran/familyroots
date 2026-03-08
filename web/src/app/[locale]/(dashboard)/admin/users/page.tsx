'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { PendingUsersList } from '@/components/admin/PendingUsersList'
import { RoleSelector } from '@/components/admin/RoleSelector'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api/axios'

type ClanRole = 'admin' | 'editor' | 'viewer'

interface ClanMember {
  id: string
  full_name: string
  email: string
  avatar_url?: string | null
  role: ClanRole
  is_approved: boolean
  created_at: string
}

export default function AdminUsersPage() {
  const t = useTranslations('admin')
  const qc = useQueryClient()

  const { data, isLoading } = useQuery<ClanMember[]>({
    queryKey: ['admin', 'users'],
    queryFn: async () => {
      const res = await api.get<{ data: ClanMember[] }>('/clans/me/members')
      return res.data.data
    },
  })

  const approveMutation = useMutation({
    mutationFn: (userId: string) => api.patch(`/clans/me/members/${userId}/approve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  })

  const rejectMutation = useMutation({
    mutationFn: (userId: string) => api.delete(`/clans/me/members/${userId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  })

  const rolesMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: ClanRole }) =>
      api.patch(`/clans/me/members/${userId}/role`, { role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  })

  const pending = data?.filter(u => !u.is_approved) ?? []
  const approved = data?.filter(u => u.is_approved) ?? []

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="font-serif text-2xl text-gray-800">{t('users_title')}</h1>

      <section className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          {t('pending_approval')}
        </h2>
        <PendingUsersList
          users={pending}
          isLoading={isLoading}
          onApprove={id => approveMutation.mutate(id)}
          onReject={id => rejectMutation.mutate(id)}
        />
      </section>

      <section className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          {t('all_members')}
        </h2>
        {approved.map(user => (
          <div key={user.id} className="flex items-center justify-between py-2 border-b last:border-0 border-gray-50">
            <div>
              <p className="text-sm font-medium text-gray-700">{user.full_name}</p>
              <p className="text-xs text-gray-400">{user.email}</p>
            </div>
            <RoleSelector
              value={user.role}
              onChange={role => rolesMutation.mutate({ userId: user.id, role })}
            />
          </div>
        ))}
      </section>
    </div>
  )
}
