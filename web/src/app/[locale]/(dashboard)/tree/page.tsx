'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { TreeCanvas } from '@/components/family-tree/TreeCanvas'
import { MemberSidebar } from '@/components/family-tree/MemberSidebar'
import { useAuthStore } from '@/store/auth.store'

export default function TreePage() {
  const t = useTranslations('tree')
  const { user } = useAuthStore()
  const clanId = user?.clan_id
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null)

  // rootMemberId defaults to clan root — ideally this comes from clan config
  // For now use a known anchor or let useFamilyTree handle the clan root
  const rootMemberId = 'root'

  return (
    <div className="h-[calc(100vh-5rem)] relative">
      <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-4 py-2 bg-cream/80 backdrop-blur-sm border-b border-gray-100">
        <h1 className="font-serif text-lg text-gray-800">{t('page_title')}</h1>
      </div>

      <div className="pt-12 h-full">
        <TreeCanvas rootMemberId={rootMemberId} />
      </div>

      {selectedMemberId && (
        <MemberSidebar
          memberId={selectedMemberId}
          onClose={() => setSelectedMemberId(null)}
        />
      )}
    </div>
  )
}
