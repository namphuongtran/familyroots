'use client'

import { Fragment, type ReactNode } from 'react'
import { useTranslations } from 'next-intl'
import { isSupabaseConfigured } from '@/lib/supabase/config'

/**
 * The hint names `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` literally, in
 * every locale (`grep -n missing_supabase_config_hint web/messages/*.json`) — they are real env
 * var names, not translatable content. Both are one unbreakable word to a browser: no space, no
 * hyphen, nothing but underscores. At 320px width and 200% root font size the hint's own column
 * (the banner's `px-4` plus the page's `px-4` and `max-w-sm`, all of which scale with the root
 * font size too) is far narrower than either token, so the whole page scrolled sideways (the banner spec,
 * measured 2026-08-22: page `scrollWidth` 569 vs `clientWidth` 320; the hint paragraph 504 vs
 * 190). This is the same defect shape the text-scale spec fixed on the `FamilyRoots` wordmark
 * (`.claude/rules/tailwind.md` § 7), and the fix is the same shape too: `<wbr />` after each
 * underscore gives the browser a break *opportunity* it uses only when the line does not fit, so
 * the token stays on one line at every normal size and `textContent` is unchanged — nothing a
 * screen reader announces changes, and copy-paste still yields the exact variable name. Do not
 * replace this with `break-words` (breaks inside a segment too) or a smaller `text-*` class
 * (traps 2 and 3 in the same section): the fix has to add break points, not remove information —
 * shrinking the type doesn't reach, and the whole value of this banner is naming the two missing
 * variables, so a fix that reads them off the screen closes the defect by deleting the feature.
 *
 * Splitting on `_` and reinserting `<wbr />` works on the *whole* translated string, not just
 * the two known tokens, so it needs no `t.rich` markup in four locale files and no hardcoded
 * copy of either variable name: every locale's hint text has no other underscore in it (checked
 * 2026-08-22), so every segment that isn't part of a token round-trips unchanged.
 */
function withBreakOpportunities(text: string): ReactNode {
  const segments = text.split('_')
  return segments.map((segment, index) => (
    <Fragment key={index}>
      {segment}
      {index < segments.length - 1 && (
        <>
          _<wbr />
        </>
      )}
    </Fragment>
  ))
}

export function SupabaseSetupNotice() {
  const t = useTranslations('auth')

  if (isSupabaseConfigured()) {
    return null
  }

  return (
    <div className="border-accent-foreground/30 bg-accent text-accent-foreground rounded-xl border px-4 py-3 text-sm">
      <p className="font-medium">{t('missing_supabase_config_title')}</p>
      <p className="text-accent-foreground mt-1">
        {withBreakOpportunities(t('missing_supabase_config_hint'))}
      </p>
    </div>
  )
}
