'use client'

// PROTOTYPE — throwaway. Floating variant switcher for `?variant=` prototypes.
// Sized in px on purpose, so the "200% text" toggle scales the page but not this bar.

import { useCallback, useEffect, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'

const SCALE_STYLE_ID = 'prototype-text-scale'

export function PrototypeSwitcher({
  variants,
}: {
  variants: ReadonlyArray<{ key: string; name: string }>
}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const current = searchParams.get('variant') ?? variants[0].key
  const index = Math.max(
    0,
    variants.findIndex((v) => v.key === current),
  )
  const [doubled, setDoubled] = useState(searchParams.get('text') === '200')

  const go = useCallback(
    (step: number) => {
      const next = variants[(index + step + variants.length) % variants.length]
      const params = new URLSearchParams(searchParams.toString())
      params.set('variant', next.key)
      router.replace(`${pathname}?${params.toString()}`)
    },
    [index, pathname, router, searchParams, variants],
  )

  // The same lever the e2e suites use: a stylesheet, not an inline style on React-owned <html>.
  useEffect(() => {
    document.getElementById(SCALE_STYLE_ID)?.remove()
    if (doubled) {
      const tag = document.createElement('style')
      tag.id = SCALE_STYLE_ID
      tag.textContent = ':root { font-size: 32px; }'
      document.head.appendChild(tag)
    }
    const params = new URLSearchParams(searchParams.toString())
    if (doubled) params.set('text', '200')
    else params.delete('text')
    if (params.toString() !== searchParams.toString()) {
      router.replace(`${pathname}?${params.toString()}`)
    }
  }, [doubled, pathname, router, searchParams])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = document.activeElement
      if (
        el instanceof HTMLInputElement ||
        el instanceof HTMLTextAreaElement ||
        (el instanceof HTMLElement && el.isContentEditable)
      )
        return
      if (e.key === 'ArrowLeft') go(-1)
      if (e.key === 'ArrowRight') go(1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go])

  if (process.env.NODE_ENV === 'production') return null

  return (
    <div
      data-prototype-switcher
      className="fixed bottom-[12px] left-1/2 z-[9999] flex -translate-x-1/2 items-center gap-[6px] rounded-full bg-[#111] px-[8px] py-[6px] text-[13px] leading-[18px] text-white shadow-[0_4px_16px_rgba(0,0,0,0.35)]"
    >
      <button
        onClick={() => go(-1)}
        className="rounded-full px-[8px] py-[2px] hover:bg-white/20"
        aria-label="Previous variant"
      >
        ←
      </button>
      <span className="font-mono whitespace-nowrap">
        {variants[index].key} ({variants[index].name})
      </span>
      <button
        onClick={() => go(1)}
        className="rounded-full px-[8px] py-[2px] hover:bg-white/20"
        aria-label="Next variant"
      >
        →
      </button>
      <button
        onClick={() => setDoubled((d) => !d)}
        className={`rounded-full px-[8px] py-[2px] whitespace-nowrap ${doubled ? 'bg-white text-black' : 'hover:bg-white/20'}`}
      >
        200% text
      </button>
    </div>
  )
}
