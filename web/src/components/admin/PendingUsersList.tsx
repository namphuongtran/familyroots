'use client'

import { useTranslations } from 'next-intl'
import { CheckCircle, XCircle, Clock } from 'lucide-react'
import { MemberAvatar } from '@/components/members/MemberAvatar'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDate } from '@/lib/utils/date'

// Pending users list — fetched from the admin users endpoint
// This component accepts its data via props so it can be used from a server component

interface PendingUser {
  id: string
  label: string
  created_at: string
  role?: string
}

interface PendingUsersListProps {
  users: PendingUser[]
  isLoading?: boolean
  onApprove: (userId: string) => void
  onReject: (userId: string) => void
}

export function PendingUsersList({ users, isLoading, onApprove, onReject }: PendingUsersListProps) {
  const t = useTranslations('admin')

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 rounded-lg border border-gray-100 p-3">
            <Skeleton className="h-10 w-10 shrink-0 rounded-full" />
            <div className="flex-1 space-y-1">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
            <Skeleton className="h-7 w-16 rounded" />
            <Skeleton className="h-7 w-16 rounded" />
          </div>
        ))}
      </div>
    )
  }

  if (users.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-gray-400">
        <CheckCircle className="h-8 w-8 opacity-40" />
        <p className="text-sm">{t('no_pending_users')}</p>
      </div>
    )
  }

  return (
    <div className="divide-y divide-gray-100">
      {users.map((user) => (
        <div key={user.id} className="flex items-center gap-3 py-3">
          <MemberAvatar fullName={user.label} gender="unknown" size="md" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-gray-800">{user.label}</p>
            {user.role && <p className="truncate text-xs text-gray-400">{user.role}</p>}
            <p className="mt-0.5 flex items-center gap-1 text-[10px] text-gray-300">
              <Clock className="h-2.5 w-2.5" />
              {formatDate(user.created_at)}
            </p>
          </div>
          <div className="flex shrink-0 gap-1.5">
            <button
              onClick={() => onApprove(user.id)}
              className="flex items-center gap-1 rounded-md border border-green-200 bg-green-50 px-2.5 py-1 text-xs text-green-700 transition-colors hover:bg-green-100"
            >
              <CheckCircle className="h-3 w-3" />
              {t('approve')}
            </button>
            <button
              onClick={() => onReject(user.id)}
              className="flex items-center gap-1 rounded-md border border-red-200 bg-red-50 px-2.5 py-1 text-xs text-red-700 transition-colors hover:bg-red-100"
            >
              <XCircle className="h-3 w-3" />
              {t('reject')}
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
