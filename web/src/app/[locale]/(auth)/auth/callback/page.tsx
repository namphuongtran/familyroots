import { redirect } from 'next/navigation'

// Supabase redirects to this page after email click — the API route at
// /api/auth/callback handles PKCE code exchange. This page is the fallback
// for in-app deep-links that haven't completed the exchange yet.
export const dynamic = 'force-dynamic'

export default async function AuthCallbackPage({
  params,
}: {
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  redirect(`/${locale}/dashboard`)
}
