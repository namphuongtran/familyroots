import type { Edge, Node } from '@xyflow/react'
import type { TreePerson, TreeSpouse } from '@/domain/tree/tree'
import { orderChildrenByMother } from '@/domain/kinship/wife-groups'
import { isKnownDate } from '@/features/persons'

/**
 * What one canvas node draws. `generation` is `undefined` on a spouse node: `SpouseNode` carries
 * no đời, so the node shows no badge rather than a guessed `Đời ?` (spec § 3.2, "never guessed").
 * On a lineage node it is `number | null`, and `null` renders `Đời ?`.
 */
export interface PersonNodeData {
  personId: string
  fullName: string
  avatarUrl: string | null
  birthYear: string | null
  deathYear: string | null
  isDeceased: boolean
  isFounder: boolean
  isPedigreeStub: boolean
  generation: number | null | undefined
  isSelected: boolean
  [key: string]: unknown
}

const NODE_WIDTH = 144 // px (w-36)
const NODE_HEIGHT = 132 // px
const H_GAP = 60 // horizontal gap between siblings
const SPOUSE_GAP = 40 // horizontal gap between member and spouse
const V_GAP = 80 // vertical gap between generations

function yearOf(date: TreePerson['birthDate']): string | null {
  return date?.date ? date.date.slice(0, 4) : null
}

function personData(person: TreePerson, selectedId: string | null): PersonNodeData {
  return {
    personId: person.id,
    fullName: person.fullName,
    avatarUrl: person.avatarUrl,
    birthYear: yearOf(person.birthDate),
    deathYear: yearOf(person.deathDate),
    isDeceased: isKnownDate(person.deathDate),
    isFounder: person.isFounder,
    isPedigreeStub: person.isPedigreeStub,
    generation: person.generation,
    isSelected: person.id === selectedId,
  }
}

function spouseData(spouse: TreeSpouse, selectedId: string | null): PersonNodeData {
  return {
    personId: spouse.id,
    fullName: spouse.fullName,
    avatarUrl: spouse.avatarUrl,
    birthYear: yearOf(spouse.birthDate),
    deathYear: yearOf(spouse.deathDate),
    isDeceased: isKnownDate(spouse.deathDate),
    isFounder: false,
    isPedigreeStub: false,
    generation: undefined,
    isSelected: spouse.id === selectedId,
  }
}

/** The children in đa thê order: each wife's children together, by `spouse_order`, `Chưa rõ mẹ` last. */
function orderedChildren(node: TreePerson): TreePerson[] {
  return orderChildrenByMother(node.children, node.spouses)
}

/** Width = max(node + spouses width, children-row width). */
function subtreeWidth(node: TreePerson): number {
  const coupleWidth = (NODE_WIDTH + SPOUSE_GAP) * (1 + node.spouses.length) - SPOUSE_GAP
  if (node.children.length === 0) return coupleWidth
  const childrenTotalWidth =
    node.children.reduce((sum, c) => sum + subtreeWidth(c), 0) + H_GAP * (node.children.length - 1)
  return Math.max(coupleWidth, childrenTotalWidth)
}

/**
 * The tree read model into React Flow nodes and edges. One row per nesting level, spouses to the
 * right of the member, children centred below in đa thê order.
 *
 * A pedigree-collapse stub (ADR-027) carries the same person id as its canonical node, so it is
 * keyed by id + parent and never enters `visited`: gating on the bare id would drop the canonical
 * subtree when the stub's branch comes first (docs/contracts/rest-tree-api.md).
 */
export function treeToFlow(
  root: TreePerson,
  selectedId: string | null = null,
): { nodes: Node<PersonNodeData>[]; edges: Edge[] } {
  const nodes: Node<PersonNodeData>[] = []
  const edges: Edge[] = []
  const visited = new Set<string>()

  function place(node: TreePerson, centreX: number, y: number, parentId?: string) {
    const isStub = node.isPedigreeStub
    if (!isStub) {
      if (visited.has(node.id)) return
      visited.add(node.id)
    }

    const nodeX = centreX - NODE_WIDTH / 2
    const flowId = isStub ? `${node.id}::stub::${parentId ?? 'root'}` : node.id

    nodes.push({
      id: flowId,
      type: 'personNode',
      position: { x: nodeX, y },
      data: personData(node, selectedId),
    })

    if (parentId) {
      edges.push({
        id: `${parentId}->${flowId}`,
        source: parentId,
        target: flowId,
        type: 'smoothstep',
        style: { stroke: '#8B6914', strokeWidth: 1.5 },
      })
    }

    // A stub's children and spouses are forced empty by the backend: display, do not descend.
    if (isStub) return

    node.spouses.forEach((spouse, i) => {
      const spouseX = nodeX + NODE_WIDTH + SPOUSE_GAP + i * (NODE_WIDTH + SPOUSE_GAP)
      if (!visited.has(spouse.id)) {
        visited.add(spouse.id)
        nodes.push({
          id: spouse.id,
          type: 'personNode',
          position: { x: spouseX, y },
          data: spouseData(spouse, selectedId),
        })
      }
      edges.push({
        id: `spouse-${node.id}-${spouse.id}`,
        source: node.id,
        target: spouse.id,
        type: 'spouseEdge',
      })
    })

    const children = orderedChildren(node)
    if (children.length === 0) return

    const totalChildWidth =
      children.reduce((sum, c) => sum + subtreeWidth(c), 0) + H_GAP * (children.length - 1)
    let childX = centreX - totalChildWidth / 2
    const childY = y + NODE_HEIGHT + V_GAP

    for (const child of children) {
      const cw = subtreeWidth(child)
      place(child, childX + cw / 2, childY, node.id)
      childX += cw + H_GAP
    }
  }

  place(root, 0, 0)
  return { nodes, edges }
}
