'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useLocale, useTranslations } from 'next-intl'
import { SupabaseSetupNotice } from '@/components/auth/SupabaseSetupNotice'
import { useAuthActions } from '@/lib/hooks/useAuth'

export default function LoginPage() {
  const t = useTranslations('auth')
  const locale = useLocale()
  const { signIn, signInWithGoogle } = useAuthActions()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isGoogleLoading, setIsGoogleLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsLoading(true)
    try {
      await signIn(email, password)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('login_error'))
    } finally {
      setIsLoading(false)
    }
  }

  const handleGoogleSignIn = async () => {
    setError(null)
    setIsGoogleLoading(true)
    try {
      await signInWithGoogle()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('login_error'))
      setIsGoogleLoading(false)
    }
  }

  return (
    <div className="bg-background flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        {/* Logo / Brand */}
        <div className="text-center">
          {/*
            `<wbr />` is load-bearing, not a typo: `FamilyRoots` is one unbreakable
            word, so at 320dp and 200% text scale it overflowed the `max-w-sm`
            column and scrolled the whole page sideways (T-04, seed S-034). A break
            opportunity is used only when the line does not fit, so the mark stays
            on one line at every normal size, and the text content stays one word.
          */}
          <h1 className="text-primary font-serif text-3xl">
            Family
            <wbr />
            Roots
          </h1>
          <p className="mt-1 text-sm text-gray-500">{t('login_subtitle')}</p>
        </div>

        <SupabaseSetupNotice />

        <form
          onSubmit={handleSubmit}
          className="space-y-4 rounded-2xl border border-gray-100 bg-white p-6 shadow-xs"
        >
          <h2 className="text-lg font-semibold text-gray-800">{t('login_title')}</h2>

          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
              {error}
            </div>
          )}

          <button
            type="button"
            onClick={handleGoogleSignIn}
            disabled={isLoading || isGoogleLoading}
            className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-800 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isGoogleLoading ? t('google_signing_in') : t('google')}
          </button>

          <div className="flex items-center gap-3 text-xs tracking-wide text-gray-400 uppercase">
            <span className="h-px flex-1 bg-gray-200" />
            <span>{t('or')}</span>
            <span className="h-px flex-1 bg-gray-200" />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">{t('email')}</label>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="focus:ring-ring w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">{t('password')}</label>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="focus:ring-ring w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="bg-primary text-primary-foreground hover:bg-primary-hover w-full rounded-lg py-2.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? t('signing_in') : t('sign_in')}
          </button>

          <p className="text-center text-xs text-gray-500">
            {t('no_account')}{' '}
            <Link href={`/${locale}/register`} className="text-primary hover:underline">
              {t('register_link')}
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
