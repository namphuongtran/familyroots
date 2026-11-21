import { describe, expect, it } from 'vitest'
import { groupChildrenByMother, orderChildrenByMother } from './wife-groups'

const WIFE_1 = { id: 'w1', fullName: 'Trần Thị Mão', spouseOrder: 1 }
const WIFE_2 = { id: 'w2', fullName: 'Lê Thị Nhàn', spouseOrder: 2 }

function child(name: string, motherId: string | null, motherSpouseOrder: number | null) {
  return { name, motherId, motherSpouseOrder }
}

describe('groupChildrenByMother', () => {
  it('orders wives by spouse_order, then the unknown-mother group last', () => {
    // The backend's order puts the second wife's child and the motherless child first.
    const children = [
      child('Bảo', null, null),
      child('Trác', 'w2', 2),
      child('Lộc', 'w1', 1),
      child('Sen', 'w1', 1),
    ]

    const groups = groupChildrenByMother(children, [WIFE_2, WIFE_1])

    expect(
      groups.map((g) =>
        g.kind === 'wife'
          ? [g.motherName, g.order, g.children.map((c) => c.name)]
          : ['unknown', null, g.children.map((c) => c.name)],
      ),
    ).toEqual([
      ['Trần Thị Mão', 1, ['Lộc', 'Sen']],
      ['Lê Thị Nhàn', 2, ['Trác']],
      ['unknown', null, ['Bảo']],
    ])
  })

  it('keeps a wife with no recorded order as a named group with no order, after the ordered ones', () => {
    const groups = groupChildrenByMother(
      [child('A', 'w3', null), child('B', 'w2', 2)],
      [WIFE_2, { id: 'w3', fullName: 'Phạm Thị Ba', spouseOrder: null }],
    )

    expect(groups.map((g) => (g.kind === 'wife' ? [g.motherName, g.order] : g.kind))).toEqual([
      ['Lê Thị Nhàn', 2],
      ['Phạm Thị Ba', null],
    ])
  })

  it('never folds a motherless child into the first wife', () => {
    const groups = groupChildrenByMother([child('A', 'w1', 1), child('B', null, null)], [WIFE_1])

    expect(groups[0]?.children.map((c) => c.name)).toEqual(['A'])
    expect(groups[1]).toEqual({ kind: 'unknown-mother', children: [child('B', null, null)] })
  })

  it('emits no unknown-mother group when every child has a mother', () => {
    const groups = groupChildrenByMother([child('A', 'w1', 1)], [WIFE_1])

    expect(groups.map((g) => g.kind)).toEqual(['wife'])
  })
})

describe('orderChildrenByMother', () => {
  it('flattens the groups in group order', () => {
    const ordered = orderChildrenByMother(
      [child('Bảo', null, null), child('Trác', 'w2', 2), child('Lộc', 'w1', 1)],
      [WIFE_1, WIFE_2],
    )

    expect(ordered.map((c) => c.name)).toEqual(['Lộc', 'Trác', 'Bảo'])
  })
})
