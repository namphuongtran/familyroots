import { getTranslations } from 'next-intl/server'
import { BackofficeDashboard } from '@/features/backoffice'

/**
 * Backoffice dashboard — landing page for clan admins. Routing only: the stats and quick actions
 * are the backoffice slice's, and its counts are read from the API, not mocked (#314).
 */
export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  const t = await getTranslations({ locale, namespace: 'Backoffice' })
  return { title: t('dashboard_title') }
}

export default async function BackofficeDashboardPage({
  params,
}: {
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  return <BackofficeDashboard locale={locale} />
}
