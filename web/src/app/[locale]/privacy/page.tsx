import { PrivacyNotice } from '@/components/legal/PrivacyNotice'
import { SiteFooter } from '@/components/layout/SiteFooter'

/** Public: `/privacy` is in `middleware.ts`'s `PUBLIC_ROUTES`, so a signed-out visitor reaches it. */
export default function PrivacyPage() {
  return (
    <div className="bg-background flex min-h-screen flex-col">
      <main className="flex-1">
        <PrivacyNotice />
      </main>
      <SiteFooter />
    </div>
  )
}
