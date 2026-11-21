'use client'

import { useMemo } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  MiniMap,
  ReactFlowProvider,
  type NodeMouseHandler,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import type { TreePerson } from '@/domain/tree/tree'
import { PersonNode } from './PersonNode'
import { SpouseEdge } from './SpouseEdge'
import { TreeControls } from './TreeControls'
import { treeToFlow, type PersonNodeData } from './tree-layout'

const NODE_TYPES = { personNode: PersonNode }
const EDGE_TYPES = { spouseEdge: SpouseEdge }

interface TreeCanvasProps {
  root: TreePerson
  selectedPersonId: string | null
  onSelectPerson: (personId: string) => void
}

/**
 * The XYFlow canvas over an already-loaded tree. Nodes are derived from the tree on every
 * render rather than held in `useNodesState`: the legacy canvas seeded that state on its first
 * render, while the query was still loading, and so never received the nodes.
 */
function TreeFlow({ root, selectedPersonId, onSelectPerson }: TreeCanvasProps) {
  const { nodes, edges } = useMemo(
    () => treeToFlow(root, selectedPersonId),
    [root, selectedPersonId],
  )

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    onSelectPerson((node.data as PersonNodeData).personId)
  }

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onNodeClick={onNodeClick}
        nodesDraggable={false}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        attributionPosition="bottom-right"
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#e5e7eb" />
        {/*
          ADR-055: one gender-neutral dot colour. `nodeColor` takes a plain string, not a CSS
          custom property, so it cannot read a token.
        */}
        <MiniMap
          nodeColor="#d1d5db"
          maskColor="rgba(0,0,0,.04)"
          className="border-border! rounded-lg! border!"
        />
        <TreeControls />
      </ReactFlow>
    </div>
  )
}

export function TreeCanvas(props: TreeCanvasProps) {
  return (
    <ReactFlowProvider>
      <TreeFlow {...props} />
    </ReactFlowProvider>
  )
}
