'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { TreeCanvas } from '@/components/family-tree/TreeCanvas'
import { MemberSidebar } from '@/components/family-tree/MemberSidebar'
import { useCurrentClanId } from '@/shared/http/context.client'

export default function TreePage() {
  const t = useTranslations('tree')
  const currentClanId = useCurrentClanId()
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(null)

  return (
    <div className="relative h-[calc(100vh-5rem)]">
      <div className="bg-background/80 border-border absolute top-0 right-0 left-0 z-10 flex items-center justify-between border-b px-4 py-2 backdrop-blur-xs">
        <h1 className="text-foreground font-serif text-lg">{t('page_title')}</h1>
      </div>

      <div className="h-full pt-12">
        <TreeCanvas rootPersonId={undefined} key={currentClanId ?? 'no-clan'} />
      </div>

      {selectedPersonId && (
        <MemberSidebar personId={selectedPersonId} onClose={() => setSelectedPersonId(null)} />
      )}
    </div>
  )
}
