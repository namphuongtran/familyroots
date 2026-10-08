import { cn } from '@/lib/utils/cn'

/**
 * The success and expired states of an email-link landing (#200, #201): a tinted panel, and the
 * actions below it on the page ground. The heading takes focus when a press replaces the form,
 * so it is focusable but out of the tab order.
 */
export function AuthOutcome({
  tone,
  icon,
  heading,
  headingRef,
  body,
  children,
}: {
  /** The panel's ground and ink, a container token pair. */
  tone: string
  icon: React.ReactNode
  heading: string
  headingRef: React.RefObject<HTMLHeadingElement | null>
  body: string
  children: React.ReactNode
}) {
  return (
    <div className="bg-background flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm space-y-6 text-center">
        <div className={cn('space-y-4 rounded-2xl px-6 py-8', tone)}>
          {icon}
          <h1 ref={headingRef} tabIndex={-1} className="font-serif text-2xl focus:outline-hidden">
            {heading}
          </h1>
          <p className="text-sm">{body}</p>
        </div>
        <div className="flex flex-col items-center gap-3">{children}</div>
      </div>
    </div>
  )
}
