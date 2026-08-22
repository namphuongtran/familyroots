import { Skeleton } from '@/components/ui/skeleton'

/**
 * Matches `PersonProfile`'s real geometry — the centred avatar circle, the
 * name line, and a handful of label/value rows — so the swap to real
 * content moves no pixel (`T-09`).
 *
 * The avatar circle and the two name-line bars are pixel-fixed arbitrary
 * values, not `rem`-based Tailwind sizes — see `PersonAvatar`'s doc comment.
 * `w-40` alone (`10rem`) is 320px once `T-04`'s check sets the root font
 * size to 32px — the entire 320dp viewport width from one decorative bar.
 */
export default function MemberDetailLoading() {
  return (
    <div className="mx-auto max-w-2xl space-y-6" aria-hidden="true">
      <div className="flex flex-col items-center gap-2">
        <Skeleton className="h-[96px] w-[96px] rounded-full" />
        <Skeleton className="h-[24px] w-[160px]" />
        <Skeleton className="h-[16px] w-[128px]" />
      </div>
      <div className="space-y-2">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-[16px] w-full" />
        ))}
      </div>
    </div>
  )
}
