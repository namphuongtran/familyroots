'use client'

import { useRef, useCallback } from 'react'
import { useTranslations } from 'next-intl'
import { MemberCard } from './MemberCard'
import { Skeleton } from '@/components/ui/skeleton'
import { usePersons } from '@/lib/hooks/useMembers'

export function MemberList() {
  const t = useTranslations('members')
  const { data, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } = usePersons()

  const observer = useRef<IntersectionObserver | null>(null)
  const sentinelRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (isFetchingNextPage) return
      if (observer.current) observer.current.disconnect()
      if (!node) return
      observer.current = new IntersectionObserver(entries => {
        if (entries[0].isIntersecting && hasNextPage) {
          fetchNextPage()
        }
      })
      observer.current.observe(node)
    },
    [isFetchingNextPage, hasNextPage, fetchNextPage],
  )

  const persons = data?.pages.flatMap(p => p.data) ?? []

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 p-3 rounded-lg border border-cream-200">
            <Skeleton className="h-10 w-10 rounded-full shrink-0" />
            <div className="flex-1 space-y-1">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-24" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (persons.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        <p className="text-sm">{t('no_members')}</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {persons.map(person => (
        <MemberCard key={person.id} member={person} />
      ))}

      {/* infinite scroll sentinel */}
      <div ref={sentinelRef} className="h-4" />

      {isFetchingNextPage && (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 p-3 rounded-lg border border-cream-200">
              <Skeleton className="h-10 w-10 rounded-full shrink-0" />
              <div className="flex-1 space-y-1">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-24" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
