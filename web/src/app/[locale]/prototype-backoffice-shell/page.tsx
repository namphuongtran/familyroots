// PROTOTYPE — throwaway, issue #162. Never merge to main.
// The real backoffice dashboard content, wrapped in four candidate shells, outside the role gate.
//
// Run:   cd web && pnpm prototype:backoffice-shell
//        (blanks the Supabase variables so middleware skips the session check)
// Open:  http://localhost:3199/vi/prototype-backoffice-shell?variant=A
//        (localhost, not 127.0.0.1: Next 16 blocks dev resources cross-origin and the page
//        never hydrates). Bottom bar: arrows or ←/→ switch variants, "200% text" sets a 32px root.
// Measure: with the server up, `node 'src/app/[locale]/prototype-backoffice-shell/measure.mjs'`
//        from web/ rewrites shots/ and prints the readings quoted on issue #162.
//
// Verdict (2026-10-04): variant A, the drawer below 1024px, as spec § 6 already prescribes.

import { Suspense } from 'react'
import BackofficeDashboardPage from '../backoffice/dashboard/page'
import { ShellPrototype } from './ShellPrototype'

export default async function PrototypeBackofficeShellPage({
  params,
}: {
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  return (
    <Suspense>
      <ShellPrototype locale={locale}>
        <BackofficeDashboardPage params={params} />
      </ShellPrototype>
    </Suspense>
  )
}
