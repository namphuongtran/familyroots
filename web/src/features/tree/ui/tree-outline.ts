import type { TreePerson } from '@/domain/tree/tree'
import { groupChildrenByMother } from '@/domain/kinship/wife-groups'

/**
 * The list view's model (spec T-08): the same people the canvas draws, as a nested outline with
 * each father's children under wife groups (§ 3.3).
 *
 * It walks the tree itself rather than reading `treeToFlow`'s nodes, so a test that compares the
 * two catches a person one of them drops. The rules match the canvas: a canonical person and a
 * spouse appear once, the first time the depth-first walk meets them, and a pedigree-collapse stub
 * (ADR-027) appears every time, with no spouses and no children of its own.
 */
export interface OutlineSpouse {
  key: string
  personId: string
  fullName: string
}

export interface OutlinePerson {
  key: string
  personId: string
  fullName: string
  generation: number | null
  isPedigreeStub: boolean
  spouses: OutlineSpouse[]
  groups: OutlineGroup[]
}

export type OutlineGroup =
  | {
      kind: 'wife'
      key: string
      motherName: string | null
      order: number | null
      children: OutlinePerson[]
    }
  | { kind: 'unknown-mother'; key: string; children: OutlinePerson[] }

export function treeToOutline(root: TreePerson): OutlinePerson {
  const visited = new Set<string>()

  function walk(node: TreePerson, parentKey: string): OutlinePerson | null {
    if (node.isPedigreeStub) {
      return {
        key: `${node.id}::stub::${parentKey}`,
        personId: node.id,
        fullName: node.fullName,
        generation: node.generation,
        isPedigreeStub: true,
        spouses: [],
        groups: [],
      }
    }
    if (visited.has(node.id)) return null
    visited.add(node.id)

    const spouses: OutlineSpouse[] = []
    for (const spouse of node.spouses) {
      if (visited.has(spouse.id)) continue
      visited.add(spouse.id)
      spouses.push({ key: spouse.id, personId: spouse.id, fullName: spouse.fullName })
    }

    const groups: OutlineGroup[] = []
    for (const group of groupChildrenByMother(node.children, node.spouses)) {
      const children = group.children
        .map((child) => walk(child, node.id))
        .filter((child): child is OutlinePerson => child !== null)
      if (children.length === 0) continue
      groups.push(
        group.kind === 'wife'
          ? {
              kind: 'wife',
              key: `${node.id}::wife::${group.motherId}`,
              motherName: group.motherName,
              order: group.order,
              children,
            }
          : { kind: 'unknown-mother', key: `${node.id}::unknown-mother`, children },
      )
    }

    return {
      key: node.id,
      personId: node.id,
      fullName: node.fullName,
      generation: node.generation,
      isPedigreeStub: false,
      spouses,
      groups,
    }
  }

  // The root is never a stub and never already visited, so the walk always returns it.
  return walk(root, 'root')!
}
