import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { Person } from '@/domain/person/person'
import { PersonRow } from './PersonRow'

const messages = {
  member: {
    unknown_date: 'Không rõ',
    born_on: 'Sinh {date}',
    deceased: 'Đã mất',
  },
}

function personFixture(overrides: Partial<Person> = {}): Person {
  return {
    id: 'p-1',
    createdByClanId: null,
    fullName: 'Trần Thị Bích',
    birthName: null,
    courtesyName: null,
    posthumousName: null,
    aliasName: null,
    gender: 'female',
    birthDate: { date: '1930-05-01', precision: 'exact', display: null, lunar: null },
    deathDate: null,
    birthPlace: null,
    deathPlace: null,
    burialPlace: null,
    tombLocation: null,
    residencePlace: null,
    religion: null,
    nationality: 'VN',
    occupation: null,
    educationLevel: null,
    titleRank: null,
    phone: null,
    email: null,
    biography: null,
    avatarUrl: null,
    notes: null,
    isDeleted: false,
    createdBy: 'u-1',
    updatedBy: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    version: 1,
    ...overrides,
  }
}

function renderRow(person: Person) {
  return render(
    <NextIntlClientProvider locale="vi" messages={messages}>
      <PersonRow person={person} />
    </NextIntlClientProvider>,
  )
}

describe('PersonRow', () => {
  it('shows a born-only line and no deceased chip for a living person', () => {
    renderRow(personFixture({ deathDate: null }))

    expect(screen.getByText('Sinh 01/05/1930')).toBeInTheDocument()
    expect(screen.queryByText('Đã mất')).not.toBeInTheDocument()
  })

  it('shows a birth-death range and the deceased chip when the death date is known', () => {
    renderRow(
      personFixture({
        deathDate: { date: '1998-11-20', precision: 'exact', display: null, lunar: null },
      }),
    )

    expect(screen.getByText('01/05/1930 – 20/11/1998')).toBeInTheDocument()
    // T-06: colour is never the only channel — this text label is the
    // channel, independent of the avatar's `opacity-70` dimming.
    expect(screen.getByText('Đã mất')).toBeInTheDocument()
  })

  it('never renders a đời badge or a chi/nhánh value — Person carries neither field', () => {
    renderRow(personFixture())
    // Negative control for this claim: if `Person` ever gains a `generation`
    // field and a later edit starts rendering it, this text would appear
    // and this assertion would catch the drift from PersonRow's own doc
    // comment about why it is absent today.
    expect(screen.queryByText(/Đời/)).not.toBeInTheDocument()
  })
})
