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
      <div className="bg-purple-50 border border-purple-100 rounded-xl px-4 py-2 text-xs text-purple-700 font-medium">
        Platform Admin – Super-administrator access only
      </div>
      {children}
    </div>
  )
}
