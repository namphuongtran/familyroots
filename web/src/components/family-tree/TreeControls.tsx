'use client'

import { useTranslations } from 'next-intl'
import { ZoomIn, ZoomOut, Maximize2, GitBranch } from 'lucide-react'
import { useReactFlow } from '@xyflow/react'
import { useUIStore } from '@/store/ui.store'

export function TreeControls() {
  const t = useTranslations('tree')
  const { zoomIn, zoomOut, fitView } = useReactFlow()
  const { treeMaxGenerations, setTreeMaxGenerations } = useUIStore()

  return (
    <div className="absolute top-3 right-3 z-10 flex flex-col gap-1.5">
      <button
        onClick={() => zoomIn()}
        title={t('zoom_in')}
        className="w-8 h-8 flex items-center justify-center rounded-md bg-white border border-gray-200 shadow-xs hover:bg-gray-50"
      >
        <ZoomIn className="h-4 w-4 text-gray-600" />
      </button>

      <button
        onClick={() => zoomOut()}
        title={t('zoom_out')}
        className="w-8 h-8 flex items-center justify-center rounded-md bg-white border border-gray-200 shadow-xs hover:bg-gray-50"
      >
        <ZoomOut className="h-4 w-4 text-gray-600" />
      </button>

      <button
        onClick={() => fitView({ padding: 0.15, duration: 400 })}
        title={t('fit_view')}
        className="w-8 h-8 flex items-center justify-center rounded-md bg-white border border-gray-200 shadow-xs hover:bg-gray-50"
      >
        <Maximize2 className="h-4 w-4 text-gray-600" />
      </button>

      {/* Generation depth selector */}
      <div className="mt-2 flex flex-col gap-1 bg-white border border-gray-200 rounded-md shadow-xs p-2 w-28 text-xs">
        <div className="flex items-center gap-1 text-gray-500">
          <GitBranch className="h-3 w-3" />
          {t('generations')}
        </div>
        <input
          type="range"
          min={2}
          max={10}
          step={1}
          value={treeMaxGenerations}
          onChange={e => setTreeMaxGenerations(Number(e.target.value))}
          className="accent-primary w-full"
        />
        <div className="text-center font-semibold text-primary">{treeMaxGenerations}</div>
      </div>
    </div>
  )
}
