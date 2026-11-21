import { useTranslations } from 'next-intl'

/** Each section is one heading and the paragraphs under it, in reading order. */
const SECTIONS = [
  { title: 'collect_title', bodies: ['collect_body'] },
  { title: 'purpose_title', bodies: ['purpose_body'] },
  { title: 'visibility_title', bodies: ['visibility_body'] },
  { title: 'storage_title', bodies: ['storage_body'] },
  { title: 'rights_title', bodies: ['rights_delete_body', 'rights_anonymise_body'] },
  { title: 'contact_title', bodies: ['contact_body'] },
] as const

/**
 * The privacy notice (#333). Public (`PUBLIC_ROUTES` in `middleware.ts`): it is linked from
 * sign-up, where the reader has no session. The text is a draft until #322 decides the data
 * controller and the legal review closes, and the banner says so on the page itself.
 */
export default function PrivacyPage() {
  const t = useTranslations('privacy')
  return (
    <main className="bg-background min-h-screen px-4 py-10">
      <article className="mx-auto w-full max-w-2xl space-y-6">
        <p
          role="note"
          className="bg-warning-container text-warning-container-foreground rounded-md px-3 py-2 text-sm font-medium"
        >
          {t('draft_banner')}
        </p>
        <h1 className="text-foreground font-serif text-3xl">{t('title')}</h1>
        <p className="text-muted-foreground text-sm">{t('intro')}</p>
        {SECTIONS.map(({ title, bodies }) => (
          <section key={title} className="space-y-2">
            <h2 className="text-foreground text-lg font-semibold">{t(title)}</h2>
            {bodies.map((body) => (
              <p key={body} className="text-muted-foreground text-sm">
                {t(body)}
              </p>
            ))}
          </section>
        ))}
      </article>
    </main>
  )
}
