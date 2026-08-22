import { requireRole } from '@/lib/utils/with-role'

export default async function AdminLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  // Server-side guard: only admin and super_admin may enter this section
  await requireRole(['admin', 'super_admin'], locale)

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-red-100 bg-red-50 px-4 py-2 text-xs font-medium text-red-600">
        Khu vực quản trị – chỉ quản trị viên dòng họ mới có quyền truy cập
      </div>
      {children}
    </div>
  )
}
