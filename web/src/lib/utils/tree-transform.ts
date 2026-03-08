import type { Node, Edge } from '@xyflow/react'
import type { TreeNode, SpouseNode } from '@/lib/types/tree'

export interface MemberNodeData {
  member: TreeNode
  isDeceased: boolean
  isFounder: boolean
  isOutsideClan: boolean
  [key: string]: unknown
}

const NODE_WIDTH = 144   // px (w-36)
const NODE_HEIGHT = 120  // px
const H_GAP = 60         // horizontal gap between siblings
const SPOUSE_GAP = 40    // horizontal gap between member and spouse
const V_GAP = 80         // vertical gap between generations

function spouseNodeData(
  spouse: SpouseNode,
  depth: number,
): MemberNodeData {
  return {
    member: {
      ...spouse,
      birth_name: undefined,
      birth_date_approx: false,
      death_date_approx: false,
      is_clan_founder: false,
      is_clan_member: false,
      birth_place: undefined,
      generation: undefined,
      depth,
      spouses: [],
      children: [],
    },
    isDeceased: !!spouse.death_date,
    isFounder: false,
    isOutsideClan: true,
  }
}

/**
 * Recursively compute the total width needed for a subtree rooted at `node`.
 * Width = max(node + spouses width, children-row width)
 */
function subtreeWidth(node: TreeNode): number {
  const coupleWidth =
    (NODE_WIDTH + SPOUSE_GAP) * (1 + node.spouses.length) - SPOUSE_GAP

  if (node.children.length === 0) return coupleWidth

  const childrenTotalWidth =
    node.children.reduce((sum, c) => sum + subtreeWidth(c), 0) +
    H_GAP * (node.children.length - 1)

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

  function processNode(
    node: TreeNode,
    centreX: number,
    y: number,
    parentId?: string,
  ) {
    if (visited.has(node.id)) return
    visited.add(node.id)

    const nodeX = centreX - NODE_WIDTH / 2

    nodes.push({
      id: node.id,
      type: 'memberNode',
      position: { x: nodeX, y },
      data: {
        member: node,
        isDeceased: !!node.death_date,
        isFounder: node.is_clan_founder,
        isOutsideClan: !node.is_clan_member,
      } satisfies MemberNodeData,
    })

    // Parent → child edge
    if (parentId) {
      edges.push({
        id: `${parentId}->${node.id}`,
        source: parentId,
        target: node.id,
        type: 'smoothstep',
        style: { stroke: '#8B6914', strokeWidth: 1.5 },
      })
    }

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
          subtype: spouse.relation_subtype,
          is_primary: spouse.is_primary,
        },
        style: { stroke: spouse.end_date ? '#999' : '#C41E3A' },
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
