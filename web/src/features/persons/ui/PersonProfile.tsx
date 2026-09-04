import { getLocale, getTranslations } from 'next-intl/server'
import Link from 'next/link'
import { lunarLabel } from '@/domain/date/historical-date'
import type { Person } from '@/domain/person/person'
import { formatHistoricalDate, isKnownDate, personHasVisibleDetail } from './format-person-date'
import { PersonAvatar } from './PersonAvatar'

interface PersonProfileProps {
  person: Person
  /** Editor or admin — gates the "Bổ sung thông tin" link on a sparse record. */
  canEdit: boolean
  /** Admin only — gates the audit line and the soft-delete banner's full detail. */
  isAdmin: boolean
}

interface Field {
  label: string
  value: string | null
}

function Fields({ fields }: { fields: Field[] }) {
  const present = fields.filter((field): field is { label: string; value: string } =>
    Boolean(field.value),
  )
  if (present.length === 0) return null
  return (
    <dl className="space-y-2">
      {present.map((field) => (
        <div key={field.label} className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
          <dt className="text-muted-foreground text-sm sm:w-[160px] sm:shrink-0">{field.label}</dt>
          <dd className="text-foreground text-sm">{field.value}</dd>
        </div>
      ))}
    </dl>
  )
}

/**
 * Spec §7.6, "Hồ sơ một người". A Server Component — `getPerson` runs
 * in `page.tsx` and this only ever formats what it returns; nothing here is
 * interactive except the native `<details>` for a long biography, so this
 * needs no client boundary of its own.
 *
 * **Two sections in the spec are not built.** §5 "Quan hệ" (parents,
 * spouses, children) and §6 "Ảnh & tài liệu" both need slices that have not
 * landed — `relationships` and `documents` — and `Person` (`GET
 * /persons/{id}`) carries neither. This seed's own "Out of scope" line names
 * "the tree"; the relationship *edges* a profile would need are the same
 * unbuilt surface. Rendering an empty section for either would be a false
 * claim that the data was checked and found absent, so both are omitted
 * entirely rather than shown empty.
 *
 * **The desktop "main 1fr / aside 360px" split (spec §7.6, ≥1280) is not
 * built.** The spec itself says a detail screen "may" split, and everything
 * that split would move into the aside here — relationships, quick actions —
 * is one of the two omitted sections above. A single centred column at every
 * width is what is actually built; see this component's own render below.
 */
export async function PersonProfile({ person, canEdit, isAdmin }: PersonProfileProps) {
  const t = await getTranslations('member')
  const locale = await getLocale()
  const unknown = t('unknown_date')

  const deceased = isKnownDate(person.deathDate)
  const birthLunar = lunarLabel(person.birthDate)
  const deathLunar = lunarLabel(person.deathDate)

  const nameFields: Field[] = [
    { label: t('birth_name'), value: person.birthName },
    { label: t('courtesy_name'), value: person.courtesyName },
    { label: t('posthumous_name'), value: person.posthumousName },
    { label: t('alias_name'), value: person.aliasName },
    { label: t('title_rank'), value: person.titleRank },
  ]
  const placeFields: Field[] = [
    { label: t('birth_place'), value: person.birthPlace },
    { label: t('death_place'), value: person.deathPlace },
    { label: t('residence_place'), value: person.residencePlace },
    { label: t('burial_place'), value: person.burialPlace },
    { label: t('tomb_location'), value: person.tombLocation },
  ]

  const hasNameFields = nameFields.some((field) => field.value)
  const hasPlaceFields = placeFields.some((field) => field.value)
  const hasAnyDate = isKnownDate(person.birthDate) || isKnownDate(person.deathDate)
  const hasBiography = Boolean(person.biography)
  const hasNotes = Boolean(person.notes)
  const isSparse = !personHasVisibleDetail(person)

  const updatedLabel = new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(
    new Date(person.updatedAt),
  )

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/**
       * §7.6's soft-delete banner. `docs/contracts/rest-persons-api.md:88-92`
       * documents that no list under `/persons` ever contains an id
       * `GET /persons/{id}` answers 404 for, with no documented query param
       * to bypass that for an admin — so `person.isDeleted` cannot be true
       * on a value this component ever actually receives today. The branch
       * stays, guarded by the source note above, rather than silently
       * dropped: a future contract change that adds an admin bypass would
       * make it reachable without anyone remembering to add it back.
       */}
      {person.isDeleted && (
        <div className="bg-heritage-container text-heritage-container-foreground rounded-2xl p-4 text-sm">
          {t('deleted_banner')}
        </div>
      )}

      <div className="flex flex-col items-center gap-2 text-center">
        <PersonAvatar
          fullName={person.fullName}
          avatarUrl={person.avatarUrl}
          size="lg"
          isDeceased={deceased}
        />
        <h1 className="text-foreground font-serif text-2xl">{person.fullName}</h1>
        <p className="text-muted-foreground text-sm">
          {formatHistoricalDate(person.birthDate, locale, unknown)}
          {' – '}
          {deceased ? formatHistoricalDate(person.deathDate, locale, unknown) : t('alive')}
        </p>
        <p className="text-muted-foreground text-xs">{t(`gender_${person.gender}`)}</p>
        {deceased && (
          <span className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-[11px]">
            {t('deceased')}
          </span>
        )}
        {canEdit && (
          <Link
            href="./edit"
            className="border-input text-foreground hover:bg-muted focus:ring-ring mt-2 rounded-full border px-3 py-1.5 text-sm transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none"
          >
            {t('edit')}
          </Link>
        )}
      </div>

      {isSparse ? (
        <p className="bg-muted text-muted-foreground rounded-2xl p-4 text-sm">
          {t('sparse_notice')}
          {canEdit && (
            <>
              {' '}
              <Link href="./edit" className="text-primary font-medium hover:underline">
                {t('add_info')}
              </Link>
            </>
          )}
        </p>
      ) : (
        <>
          {hasNameFields && (
            <section className="space-y-2">
              <h2 className="text-foreground text-sm font-semibold">{t('names_section')}</h2>
              <Fields fields={nameFields} />
            </section>
          )}

          {hasAnyDate && (
            <section className="space-y-2">
              <h2 className="text-foreground text-sm font-semibold">{t('dates_section')}</h2>
              <dl className="space-y-2">
                <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
                  <dt className="text-muted-foreground text-sm sm:w-[160px] sm:shrink-0">
                    {t('birth_date')}
                  </dt>
                  <dd className="text-foreground text-sm">
                    {formatHistoricalDate(person.birthDate, locale, unknown)}
                    {birthLunar && (
                      <span className="text-muted-foreground block text-xs">
                        {t('lunar_line', { lunar: birthLunar })}
                      </span>
                    )}
                  </dd>
                </div>
                <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
                  <dt className="text-muted-foreground text-sm sm:w-[160px] sm:shrink-0">
                    {t('death_date')}
                  </dt>
                  <dd className="text-foreground text-sm">
                    {formatHistoricalDate(person.deathDate, locale, unknown)}
                    {deathLunar && (
                      <span className="text-muted-foreground block text-xs">
                        {t('lunar_line', { lunar: deathLunar })}
                      </span>
                    )}
                  </dd>
                </div>
              </dl>
            </section>
          )}

          {hasPlaceFields && (
            <section className="space-y-2">
              <h2 className="text-foreground text-sm font-semibold">{t('places_section')}</h2>
              <Fields fields={placeFields} />
            </section>
          )}

          {hasBiography && (
            <section className="space-y-2">
              <h2 className="text-foreground text-sm font-semibold">{t('biography')}</h2>
              {/* Native disclosure: no client JS, keyboard-operable by default (T-07). */}
              {(person.biography as string).length > 320 ? (
                <details className="text-foreground text-sm">
                  <summary className="text-primary cursor-pointer text-sm font-medium">
                    {t('biography')}
                  </summary>
                  <p className="mt-2 max-w-prose whitespace-pre-line">{person.biography}</p>
                </details>
              ) : (
                <p className="text-foreground max-w-prose text-sm whitespace-pre-line">
                  {person.biography}
                </p>
              )}
            </section>
          )}

          {hasNotes && (
            <section className="space-y-2">
              <h2 className="text-foreground text-sm font-semibold">{t('notes')}</h2>
              <p className="text-foreground max-w-prose text-sm whitespace-pre-line">
                {person.notes}
              </p>
            </section>
          )}
        </>
      )}

      {isAdmin && (
        <p className="text-muted-foreground text-xs">{t('updated_line', { date: updatedLabel })}</p>
      )}
    </div>
  )
}
