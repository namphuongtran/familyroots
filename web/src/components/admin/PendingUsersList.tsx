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
          <div key={i} className="flex items-center gap-3 p-3 rounded-lg border border-gray-100">
            <Skeleton className="h-10 w-10 rounded-full shrink-0" />
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
      {users.map(user => (
        <div key={user.id} className="flex items-center gap-3 py-3">
          <MemberAvatar
            fullName={user.label}
            gender="unknown"
            size="md"
          />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-800 truncate">{user.label}</p>
            {user.role && <p className="text-xs text-gray-400 truncate">{user.role}</p>}
            <p className="text-[10px] text-gray-300 flex items-center gap-1 mt-0.5">
              <Clock className="h-2.5 w-2.5" />
              {formatDate(user.created_at)}
            </p>
          </div>
          <div className="flex gap-1.5 shrink-0">
            <button
              onClick={() => onApprove(user.id)}
              className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-md bg-green-50 text-green-700 hover:bg-green-100 border border-green-200 transition-colors"
            >
              <CheckCircle className="h-3 w-3" />
              {t('approve')}
            </button>
            <button
              onClick={() => onReject(user.id)}
              className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-md bg-red-50 text-red-700 hover:bg-red-100 border border-red-200 transition-colors"
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
