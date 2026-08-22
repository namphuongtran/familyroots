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
      <div className="rounded-xl border border-purple-100 bg-purple-50 px-4 py-2 text-xs font-medium text-purple-700">
        Platform Admin – Super-administrator access only
      </div>
      {children}
    </div>
  )
}
