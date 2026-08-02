'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Search, X } from 'lucide-react'
import { MemberCard } from './MemberCard'
import { Skeleton } from '@/components/ui/skeleton'
import { usePersonSearch } from '@/lib/hooks/useMembers'
import { useDebounce } from '@/lib/hooks/useDebounce'

export function MemberSearch() {
  const t = useTranslations('members')
  const [query, setQuery] = useState('')
  const debouncedQuery = useDebounce(query, 300)
  const { data, isLoading } = usePersonSearch(debouncedQuery)

  const isSearching = debouncedQuery.length >= 2
  const results = data ?? []

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder={t('search_placeholder')}
          className="w-full pl-9 pr-8 py-2 text-sm border border-gray-300 rounded-md focus:outline-hidden focus:ring-2 focus:ring-primary-500"
        />
        {query && (
          <button
            onClick={() => setQuery('')}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {isSearching && isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 p-3 rounded-lg border border-cream-200">
              <Skeleton className="h-8 w-8 rounded-full shrink-0" />
              <div className="flex-1 space-y-1">
                <Skeleton className="h-3 w-28" />
                <Skeleton className="h-2.5 w-20" />
              </div>
            </div>
          ))}
        </div>
      )}

      {isSearching && !isLoading && results.length === 0 && (
        <p className="text-sm text-center text-gray-400 py-4">{t('no_results')}</p>
      )}

      {isSearching && !isLoading && results.length > 0 && (
        <div className="space-y-1.5">
          {results.map(member => (
            <MemberCard key={member.id} member={member} />
          ))}
        </div>
      )}
    </div>
  )
}
