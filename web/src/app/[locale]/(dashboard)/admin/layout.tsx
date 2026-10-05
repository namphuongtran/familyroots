/**
 * The admin section's banner. It guards nothing itself: each page names the capability it needs
 * in its own layout (`users/layout.tsx`, `clan/layout.tsx`), because no one capability covers both
 * (#186, ADR-061 § 4). The `(dashboard)` layout above has already admitted a ready member.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-4">
      <div className="border-destructive/20 bg-destructive/10 text-destructive rounded-xl border px-4 py-2 text-xs font-medium">
        Khu vực quản trị – chỉ quản trị viên dòng họ mới có quyền truy cập
      </div>
      {children}
    </div>
  )
}
