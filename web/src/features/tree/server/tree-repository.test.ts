import { describe, expect, it, vi } from 'vitest'
import type { FetchLike } from '@/shared/http/api-client'
import { ApiError } from '@/shared/http/errors'
import type { RequestContext } from '@/shared/http/request-context'
import { FATHER_ID, WIFE_1_ID, focusViewDto, treeResponseDto } from '../model/tree-fixtures'
import { getFocus, getTree } from './tree-repository'

const context: RequestContext = { locale: 'vi', clanId: 'clan-1', accessToken: 'tok-1' }

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('getTree', () => {
  it('reads GET /tree with its query and maps the envelope into the domain tree', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () => jsonResponse({ data: treeResponseDto() }))

    const tree = await getTree({ maxGenerations: 6 }, { context, fetchImpl })

    const url = new URL((fetchImpl.mock.calls[0]?.[0] as Request).url)
    expect(url.pathname).toMatch(/\/tree$/)
    expect(url.searchParams.get('max_generations')).toBe('6')
    expect(url.searchParams.has('root_person_id')).toBe(false)

    expect(tree.totalPersons).toBe(7)
    expect(tree.root.id).toBe(FATHER_ID)
    expect(tree.root.generation).toBe(4)
    expect(tree.root.hasMoreDescendants).toBe(false)
    expect(tree.root.spouses.map((s) => [s.fullName, s.spouseOrder])).toEqual([
      ['Lê Thị Nhàn', 2],
      ['Trần Thị Mão', 1],
    ])
    const loc = tree.root.children.find((c) => c.fullName === 'Nguyễn Hữu Lộc')
    expect(loc).toMatchObject({ motherId: WIFE_1_ID, motherSpouseOrder: 1, generation: 5 })
    // A null đời stays null: never 0, never guessed.
    const bao = tree.root.children.find((c) => c.fullName === 'Nguyễn Hữu Bảo')
    expect(bao).toMatchObject({ motherId: null, motherSpouseOrder: null, generation: null })
    expect(bao?.birthDate).toEqual({
      date: '1900-01-01',
      precision: 'year',
      display: '1900',
      lunar: null,
    })
  })

  it('surfaces 404 clan_founder_not_found as an ApiError with that code', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse(
        { error: { code: 'clan_founder_not_found', message: 'x', detail: {} } },
        { status: 404 },
      ),
    )

    const error = await getTree({}, { context, fetchImpl }).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('clan_founder_not_found')
  })
})

describe('getFocus', () => {
  it('reads GET /tree/focus/{id} and maps ancestors, đời and the focus-only fields', async () => {
    const dto = focusViewDto()
    dto.focus_subtree!.has_more_descendants = true
    const fetchImpl = vi.fn<FetchLike>(async () => jsonResponse({ data: dto }))

    const view = await getFocus(FATHER_ID, { descendants: 1 }, { context, fetchImpl })

    const url = new URL((fetchImpl.mock.calls[0]?.[0] as Request).url)
    expect(url.pathname).toMatch(new RegExp(`/tree/focus/${FATHER_ID}$`))
    expect(url.searchParams.get('descendants')).toBe('1')

    expect(view.generationOfFocus).toBe(4)
    expect(view.ancestors).toEqual([
      {
        id: '00000000-0000-0000-0000-000000000099',
        fullName: 'Nguyễn Hữu Tổ',
        gender: 'male',
        avatarUrl: null,
        generation: 1,
        isFounder: true,
      },
    ])
    expect(view.subtree?.hasMoreDescendants).toBe(true)
    expect(view.subtree?.children).toHaveLength(4)
  })

  it('rejects a body whose node lacks a required field', async () => {
    const dto = focusViewDto() as unknown as { focus_subtree: Record<string, unknown> }
    delete dto.focus_subtree.pedigree_collapse_ref
    const fetchImpl = vi.fn<FetchLike>(async () => jsonResponse({ data: dto }))

    await expect(getFocus(FATHER_ID, {}, { context, fetchImpl })).rejects.toThrow()
  })
})
