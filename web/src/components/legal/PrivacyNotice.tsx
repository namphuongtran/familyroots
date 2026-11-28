'use client'

import { useTranslations } from 'next-intl'

/**
 * The privacy notice (#333). It is a DRAFT: the banner below stays until #322 (the legal
 * review) closes, and then it is removed together with the `privacy.draft_banner` message.
 * The data controller and contact details are deliberately not named, because #322 owns them.
 */
export function PrivacyNotice() {
  const t = useTranslations('privacy')

  return (
    <article className="mx-auto w-full max-w-2xl space-y-6 px-4 py-8">
      <div
        role="note"
        className="bg-accent text-accent-foreground rounded-xl px-4 py-3 text-sm font-medium wrap-anywhere"
      >
        {t('draft_banner')}
      </div>

      <h1 className="text-primary font-serif text-3xl wrap-anywhere">{t('title')}</h1>
      <p className="text-foreground text-sm">{t('intro')}</p>

      <section className="space-y-2">
        <h2 className="text-foreground font-serif text-xl">{t('stores_title')}</h2>
        <ul className="text-foreground list-disc space-y-1 pl-5 text-sm">
          <li>{t('stores_account')}</li>
          <li>{t('stores_membership')}</li>
          <li>{t('stores_persons')}</li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-foreground font-serif text-xl">{t('hosting_title')}</h2>
        <p className="text-foreground text-sm">{t('hosting_body')}</p>
      </section>

      <section className="space-y-3">
        <h2 className="text-foreground font-serif text-xl">{t('rights_title')}</h2>
        <div className="space-y-1">
          <h3 className="text-foreground text-sm font-semibold">{t('delete_title')}</h3>
          <p className="text-foreground text-sm">{t('delete_body')}</p>
        </div>
        <div className="space-y-1">
          <h3 className="text-foreground text-sm font-semibold">{t('anonymise_title')}</h3>
          <p className="text-foreground text-sm">{t('anonymise_body')}</p>
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-foreground font-serif text-xl">{t('controller_title')}</h2>
        <p className="text-muted-foreground text-sm">{t('controller_body')}</p>
      </section>
    </article>
  )
}
