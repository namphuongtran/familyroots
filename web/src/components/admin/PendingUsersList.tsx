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
          <div key={i} className="border-border flex items-center gap-3 rounded-lg border p-3">
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
      <div className="text-muted-foreground flex flex-col items-center gap-2 py-10">
        <CheckCircle className="h-8 w-8 opacity-40" />
        <p className="text-sm">{t('no_pending_users')}</p>
      </div>
    )
  }

  return (
    <div className="divide-border divide-y">
      {users.map((user) => (
        <div key={user.id} className="flex items-center gap-3 py-3">
          <MemberAvatar fullName={user.label} gender="unknown" size="md" />
          <div className="min-w-0 flex-1">
            <p className="text-foreground truncate text-sm font-medium">{user.label}</p>
            {user.role && <p className="text-muted-foreground truncate text-xs">{user.role}</p>}
            <p className="text-muted-foreground mt-0.5 flex items-center gap-1 text-[10px]">
              <Clock className="h-2.5 w-2.5" />
              {formatDate(user.created_at)}
            </p>
          </div>
          <div className="flex shrink-0 gap-1.5">
            <button
              onClick={() => onApprove(user.id)}
              // ADR-055: mirrors the reject button's own
              // `border-destructive/30 bg-destructive/10 text-destructive`
              // shape, with the new `success` token (spec § 2.1/2.2) standing
              // in for the old untokened `border-green-200 bg-green-50
              // text-green-700`.
              className="border-success/30 bg-success/10 text-success hover:bg-success/15 flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors"
            >
              <CheckCircle className="h-3 w-3" />
              {t('approve')}
            </button>
            <button
              onClick={() => onReject(user.id)}
              className="border-destructive/30 bg-destructive/10 text-destructive hover:bg-destructive/15 flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors"
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
