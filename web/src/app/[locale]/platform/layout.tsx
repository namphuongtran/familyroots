import { requireRole } from '@/lib/utils/with-role'

export default async function PlatformLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  // Server-side guard: platform section is super_admin only
  await requireRole('super_admin', locale)

  return (
    <div className="space-y-4">
      {/*
        ADR-055: was `border-purple-100 bg-purple-50 text-purple-700`, a
        one-off untokened purple with no dark value. This banner is a
        standing notice about an elevated, cross-clan surface, the same job
        `EventCard`'s `clan_ceremony` already gives the `accent` warning pair
        (`bg-accent border-accent-foreground/30`) — reused here rather than
        inventing a second "notice" family.
      */}
      <div className="bg-accent border-accent-foreground/30 text-accent-foreground rounded-xl border px-4 py-2 text-xs font-medium">
        {/*
          This string is hardcoded English, not routed through next-intl —
          a pre-existing gap ADR-055 found and left alone: this seed decides
          colour, not copy, and touching `web/messages/*.json` is fenced to
          other agents this batch.
        */}
        Platform Admin – Super-administrator access only
      </div>
      {children}
    </div>
  )
}
