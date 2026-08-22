import { getTranslations } from 'next-intl/server'
import Link from 'next/link'
import { Plus } from 'lucide-react'
import { PersonsList } from '@/features/persons'
import { getServerAuthContext } from '@/lib/server/auth-context'

/**
 * Spec §7.5, "Danh sách thành viên" (S-031). The shell stays a Server
 * Component — the title and the role-gated "add" link need no client JS —
 * and `PersonsList` (`@/features/persons`, `ui/PersonsList.tsx`) is the one
 * Client Component boundary, because cursor pagination is inherently
 * interactive state. See that file's own doc comment for why it is the
 * button-only pagination spec §7.5 describes for the web client, not the
 * mobile auto-load variant.
 *
 * **Search and filters (spec §7.5's SearchField and filter sheet) are not
 * built here.** The seed's own end state is "paginates by cursor... renders
 * one person" — the minimal read surface `usePersonsList` (S-030) already
 * supports. Search would need `usePersonSearch` wired to a text input plus
 * a debounce, and filters need a sheet/panel neither this seed nor any
 * earlier one designed. Both are a materially larger feature than this
 * seed's text asks for, so this is a deliberate scope reduction from the
 * spec's fuller design, not an oversight.
 *
 * **Row `⋯` actions (admin: `Xóa`, `Đặt làm thủy tổ`) are not built either.**
 * `useDeletePerson`/`useRestorePerson` exist (S-030), but wiring a working
 * delete/restore action needs a confirmation and a toast pattern this
 * codebase has not established anywhere yet — inventing one here would be
 * exactly the kind of write-UX decision this seed does not own (create and
 * edit are S-032's).
 */
export default async function MembersPage() {
  const t = await getTranslations('members')
  const authContext = await getServerAuthContext()
  const canCreateMembers =
    authContext?.currentClanRole === 'editor' || authContext?.currentClanRole === 'admin'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-foreground font-serif text-2xl">{t('page_title')}</h1>
        {canCreateMembers && (
          <Link
            href="./new"
            className="bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none"
          >
            <Plus className="h-4 w-4" />
            {t('add_member')}
          </Link>
        )}
      </div>

      <PersonsList />
    </div>
  )
}
