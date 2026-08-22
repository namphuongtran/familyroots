import { PersonsListSkeleton } from '@/features/persons'

/**
 * Next's own Suspense fallback for this route segment — shown while
 * `page.tsx`'s own `await`s (role lookup) resolve. Reuses the exact skeleton
 * `PersonsList` shows for its own first-load state, so there is one row
 * geometry in this route, not two (`T-09`).
 */
export default function MembersLoading() {
  return (
    <div className="space-y-4">
      {/* Pixel-fixed, not `w-40`/`h-8` — see `PersonAvatar`'s doc comment for why a decorative placeholder is never sized in `rem` here. */}
      <div className="bg-cream-200 h-[32px] w-[160px] animate-pulse rounded-md" />
      <PersonsListSkeleton rows={8} />
    </div>
  )
}
