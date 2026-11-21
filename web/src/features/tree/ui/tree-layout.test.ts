import { describe, expect, it } from 'vitest'
import { toFamilyTree, treeResponseDtoSchema } from '../model/tree-dto'
import { FATHER_ID, treeNodeDto, treeResponseDto } from '../model/tree-fixtures'
import { treeToFlow } from './tree-layout'

function layout(dto = treeResponseDto()) {
  return treeToFlow(toFamilyTree(treeResponseDtoSchema.parse(dto)).root)
}

describe('treeToFlow', () => {
  it('places the children left to right in đa thê order: Vợ cả, Vợ hai, then Chưa rõ mẹ', () => {
    const { nodes } = layout()

    const children = nodes
      .filter((n) => n.data.generation !== undefined && n.id !== FATHER_ID)
      .sort((a, b) => a.position.x - b.position.x)
      .map((n) => n.data.fullName)

    expect(children).toEqual([
      'Nguyễn Hữu Lộc',
      'Nguyễn Thị Sen',
      'Nguyễn Hữu Trác',
      'Nguyễn Hữu Bảo',
    ])
  })

  it('carries a null đời through as null, and gives a spouse no đời at all', () => {
    const { nodes } = layout()

    const byName = new Map(nodes.map((n) => [n.data.fullName, n.data.generation]))
    expect(byName.get('Nguyễn Hữu Bảo')).toBeNull()
    expect(byName.get('Nguyễn Hữu Lộc')).toBe(5)
    expect(byName.get('Trần Thị Mão')).toBeUndefined()
  })

  it('keys a pedigree-collapse stub apart from its canonical node, and keeps the canonical subtree', () => {
    const shared = 'shared-child'
    const grandchild = treeNodeDto({ id: 'grandchild', full_name: 'Cháu' })
    const dto = treeResponseDto()
    dto.tree.children = [
      treeNodeDto({
        id: 'a',
        full_name: 'A',
        children: [treeNodeDto({ id: shared, full_name: 'Chung', pedigree_collapse_ref: true })],
      }),
      treeNodeDto({
        id: 'b',
        full_name: 'B',
        children: [treeNodeDto({ id: shared, full_name: 'Chung', children: [grandchild] })],
      }),
    ]

    const { nodes } = layout(dto)
    const ids = nodes.map((n) => n.id)

    expect(ids).toContain(`${shared}::stub::a`)
    expect(ids).toContain(shared)
    expect(ids).toContain('grandchild')
    expect(new Set(ids).size).toBe(ids.length)
  })
})
