import type { Node, Edge } from '@xyflow/react'
import type { TreeNode, SpouseNode } from '@/lib/types/tree'

export interface PersonNodeData {
  member: TreeNode
  isDeceased: boolean
  isFounder: boolean
  isOutsideClan: boolean
  [key: string]: unknown
}

const NODE_WIDTH = 144 // px (w-36)
const NODE_HEIGHT = 120 // px
const H_GAP = 60 // horizontal gap between siblings
const SPOUSE_GAP = 40 // horizontal gap between member and spouse
const V_GAP = 80 // vertical gap between generations

function spouseNodeData(spouse: SpouseNode, depth: number): PersonNodeData {
  return {
    member: {
      ...spouse,
      birth_name: undefined,
      birth_date_approx: false,
      death_date_approx: false,
      is_founder: false,
      membership_role: spouse.membership_role ?? 'spouse',
      birth_place: undefined,
      generation: undefined,
      depth,
      spouses: [],
      children: [],
    },
    isDeceased: !!spouse.death_date,
    isFounder: false,
    isOutsideClan: spouse.membership_role === 'spouse',
  }
}

/**
 * Recursively compute the total width needed for a subtree rooted at `node`.
 * Width = max(node + spouses width, children-row width)
 */
function subtreeWidth(node: TreeNode): number {
  const coupleWidth = (NODE_WIDTH + SPOUSE_GAP) * (1 + node.spouses.length) - SPOUSE_GAP

  if (node.children.length === 0) return coupleWidth

  const childrenTotalWidth =
    node.children.reduce((sum, c) => sum + subtreeWidth(c), 0) + H_GAP * (node.children.length - 1)

  return Math.max(coupleWidth, childrenTotalWidth)
}

/**
 * Transforms an API TreeNode (recursive) into React Flow nodes and edges.
 *
 * Layout:
 * - Each generation = one horizontal row (y = depth * (NODE_HEIGHT + V_GAP))
 * - Spouses placed to the right of the main member node
 * - Children distributed below their parents, centred
 */
export function treeToReactFlow(root: TreeNode): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = []
  const edges: Edge[] = []
  const visited = new Set<string>()

  function processNode(node: TreeNode, centreX: number, y: number, parentId?: string) {
    // A pedigree-collapse stub (H4) mirrors a person who also appears as a FULL
    // node elsewhere in this same payload — the same person id, twice. Stubs
    // must never gate `visited`: if a stub is reached before its canonical full
    // node (e.g. sibling ordering puts the stub's branch first), gating on the
    // bare id would make the later full node look "already visited" and drop
    // its entire subtree. Only full nodes enter `visited`; a stub encountered
    // after its full node still renders (as a leaf).
    const isStub = node.pedigree_collapse_ref === true
    if (!isStub) {
      if (visited.has(node.id)) return
      visited.add(node.id)
    }

    const nodeX = centreX - NODE_WIDTH / 2
    // React Flow requires unique node ids. Since a stub carries the same person
    // id as its canonical node, key the stub's React Flow id by id+parent so it
    // never collides with the canonical node (or with another stub of the same
    // person under a different parent). `data.member.id` keeps the real person
    // id untouched for anything reading it back out of node data.
    const flowId = isStub ? `${node.id}::stub::${parentId ?? 'root'}` : node.id

    nodes.push({
      id: flowId,
      type: 'memberNode',
      position: { x: nodeX, y },
      data: {
        member: node,
        isDeceased: !!node.death_date,
        isFounder: !!node.is_founder,
        isOutsideClan: node.membership_role === 'spouse',
      } satisfies PersonNodeData,
    })

    // Parent → child edge
    if (parentId) {
      edges.push({
        id: `${parentId}->${flowId}`,
        source: parentId,
        target: flowId,
        type: 'smoothstep',
        style: { stroke: '#8B6914', strokeWidth: 1.5 },
      })
    }

    // A stub renders as a leaf — the backend never populates its spouses or
    // children (tree_builder forces both empty), so there is nothing to recurse
    // into.
    if (isStub) return

    // Spouse nodes + spouse edges
    node.spouses.forEach((spouse, i) => {
      const spouseX = nodeX + NODE_WIDTH + SPOUSE_GAP + i * (NODE_WIDTH + SPOUSE_GAP)
      if (!visited.has(spouse.id)) {
        visited.add(spouse.id)
        nodes.push({
          id: spouse.id,
          type: 'memberNode',
          position: { x: spouseX, y },
          data: spouseNodeData(spouse, node.depth),
        })
      }
      edges.push({
        id: `spouse-${node.id}-${spouse.id}`,
        source: node.id,
        target: spouse.id,
        type: 'spouseEdge',
        data: {
          status: spouse.status,
          spouse_order: spouse.spouse_order,
        },
        style: { stroke: spouse.divorce_date ? '#999' : '#C41E3A' },
      })
    })

    // Recurse into children — centre each child's subtree
    if (node.children.length === 0) return

    const totalChildWidth =
      node.children.reduce((sum, c) => sum + subtreeWidth(c), 0) +
      H_GAP * (node.children.length - 1)

    let childX = centreX - totalChildWidth / 2
    const childY = y + NODE_HEIGHT + V_GAP

    for (const child of node.children) {
      const cw = subtreeWidth(child)
      processNode(child, childX + cw / 2, childY, node.id)
      childX += cw + H_GAP
    }
  }

  processNode(root, 0, 0)
  return { nodes, edges }
}
