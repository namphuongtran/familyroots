'use client'

import { useRouter, usePathname } from 'next/navigation'
import { useUIStore } from '@/store/ui.store'
import { cn } from '@/lib/utils/cn'

const LOCALES = [
  { code: 'vi', label: 'Tiếng Việt', flag: '🇻🇳' },
  { code: 'en', label: 'English', flag: '🇬🇧' },
  { code: 'zh', label: '中文', flag: '🇨🇳' },
  { code: 'fr', label: 'Français', flag: '🇫🇷' },
] as const

type LocaleCode = (typeof LOCALES)[number]['code']

export function LocaleSwitcher() {
  const router = useRouter()
  const pathname = usePathname()
  const { locale, setLocale } = useUIStore()

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const newLocale = e.target.value as LocaleCode
    setLocale(newLocale)
    // Replace the locale segment in the path: /vi/dashboard → /en/dashboard
    const segments = pathname.split('/')
    segments[1] = newLocale
    router.push(segments.join('/'))
  }

  return (
    <select
      value={locale}
      onChange={handleChange}
      className={cn(
        'border-cream-200 rounded-md border px-2 py-1 text-sm',
        'hover:border-primary focus:ring-ring bg-card text-foreground focus:ring-1 focus:ring-offset-2 focus:outline-hidden',
        'cursor-pointer',
      )}
      aria-label="Select language"
    >
      {LOCALES.map((l) => (
        <option key={l.code} value={l.code}>
          {l.flag} {l.label}
        </option>
      ))}
    </select>
  )
}
