'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { useAuthActions } from '@/lib/hooks/useAuth'

export default function RegisterPage() {
  const t = useTranslations('auth')
  const { signUp } = useAuthActions()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [clanAction, setClanAction] = useState<'join' | 'create'>('join')
  const [clanId, setClanId] = useState('')
  const [clanName, setClanName] = useState('')
  const [clanSlug, setClanSlug] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsLoading(true)
    try {
      const result = await signUp({
        email,
        password,
        full_name: fullName,
        clan_action: clanAction,
        clan_id: clanAction === 'join' ? clanId : undefined,
        clan_name: clanAction === 'create' ? clanName : undefined,
        clan_slug: clanAction === 'create' ? clanSlug : undefined,
      })
      setSuccess(result.message)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('register_error'))
    } finally {
      setIsLoading(false)
    }
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream px-4">
        <div className="max-w-sm w-full text-center bg-white rounded-2xl p-8 shadow-sm border border-gray-100">
          <div className="text-4xl mb-3">OK</div>
          <h2 className="font-serif text-xl text-gray-800 mb-2">{t('register_title')}</h2>
          <p className="text-sm text-gray-500">{success}</p>
          <Link href="./login" className="mt-4 inline-flex text-sm text-primary-600 hover:underline">
            {t('login_link')}
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-cream px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <h1 className="font-serif text-3xl text-primary-700">FamilyRoots</h1>
          <p className="text-sm text-gray-500 mt-1">{t('register_subtitle')}</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-gray-800">{t('register_title')}</h2>

          {error && (
            <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('full_name')}</label>
            <input
              required
              value={fullName}
              onChange={e => setFullName(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('email')}</label>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('password')}</label>
            <input
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <div className="space-y-2">
            <p className="block text-sm font-medium text-gray-700">{t('register_subtitle')}</p>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="radio"
                name="clanAction"
                checked={clanAction === 'join'}
                onChange={() => setClanAction('join')}
              />
              {t('join_clan')}
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="radio"
                name="clanAction"
                checked={clanAction === 'create'}
                onChange={() => setClanAction('create')}
              />
              {t('create_clan')}
            </label>
          </div>

          {clanAction === 'join' ? (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('clan_slug')}</label>
              <input
                required
                value={clanId}
                onChange={e => setClanId(e.target.value)}
                placeholder="UUID"
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          ) : (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('clan_name')}</label>
                <input
                  required
                  value={clanName}
                  onChange={e => setClanName(e.target.value)}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('clan_slug')}</label>
                <input
                  required
                  value={clanSlug}
                  onChange={e => setClanSlug(e.target.value)}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-2.5 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-colors"
          >
            {isLoading ? t('registering') : t('register')}
          </button>

          <p className="text-center text-xs text-gray-500">
            {t('have_account')}{' '}
            <Link href="./login" className="text-primary-600 hover:underline">
              {t('login_link')}
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
