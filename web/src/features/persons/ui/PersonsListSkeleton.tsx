import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils/cn'

interface PersonsListSkeletonProps {
  rows?: number
  className?: string
}

/**
 * Matches `PersonRow`'s real geometry (avatar + two text lines, `p-3`,
 * `rounded-2xl`, `bg-card`) so the swap from skeleton to real content moves
 * no pixel — `T-09`, spec §5. Used both by `loading.tsx` (the route's own
 * Suspense fallback) and by `PersonsList`'s own first-load and
 * loading-next-page states, so both surfaces stay pixel-identical to each
 * other as well as to the real row.
 *
 * Every dimension here is a pixel-fixed arbitrary value, not a `rem`-based
 * Tailwind size (`h-10`, `w-32`, …) — see `PersonAvatar`'s doc comment for
 * the measured `T-04` overflow that `rem` sizing caused once the root font
 * size is set to 32px. A placeholder bar is decorative, same reasoning as
 * the avatar circle: it has no reason to grow with the text scale at all.
 */
export function PersonsListSkeleton({ rows = 8, className }: PersonsListSkeletonProps) {
  return (
    <ul className={cn('space-y-2', className)} aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <li key={index} className="bg-card flex items-center gap-3 rounded-2xl p-3">
          <Skeleton className="h-[40px] w-[40px] shrink-0 rounded-full" />
          <div className="min-w-0 flex-1 space-y-1.5">
            <Skeleton className="h-[16px] w-[128px]" />
            <Skeleton className="h-[12px] w-[96px]" />
          </div>
        </li>
      ))}
    </ul>
  )
}
