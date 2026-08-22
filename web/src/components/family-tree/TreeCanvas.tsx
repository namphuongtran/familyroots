'use client'

import { useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  type NodeMouseHandler,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { MemberNode } from './MemberNode'
import { SpouseEdge } from './SpouseEdge'
import { TreeControls } from './TreeControls'
import { treeToReactFlow } from '@/lib/utils/tree-transform'
import { useFamilyTree } from '@/lib/hooks/useFamilyTree'
import { useUIStore } from '@/store/ui.store'
import { Skeleton } from '@/components/ui/skeleton'

const NODE_TYPES = { memberNode: MemberNode }
const EDGE_TYPES = { spouseEdge: SpouseEdge }

function TreeFlowInner({ rootPersonId }: { rootPersonId?: string }) {
  const { treeMaxGenerations } = useUIStore()
  const { data, isLoading } = useFamilyTree(rootPersonId, treeMaxGenerations)

  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    if (!data?.tree) return { nodes: [], edges: [] }
    return treeToReactFlow(data.tree)
  }, [data])

  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, , onEdgesChange] = useEdgesState(initialEdges)

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Skeleton className="h-64 w-64 rounded-2xl" />
      </div>
    )
  }

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        attributionPosition="bottom-right"
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#e5e7eb" />
        {/*
          ADR-055: `nodeColor` used to branch on `n.data?.gender` into three
          hexes (`#93c5fd` male, `#f9a8d4` female, `#d1d5db` other) — the same
          gender-as-only-channel defect `MemberNode` and `MemberAvatar` carried,
          and a hex besides, which cannot flip with the colour scheme at all.
          `@xyflow/react`'s `nodeColor` takes a plain string, not a CSS custom
          property, so it cannot read a token; one constant dot colour is what
          a genuinely gender-neutral minimap can be today. The minimap's own
          chrome (this panel's background, `maskColor` below) does not follow
          the app's colour scheme at all yet — a real, separate, un-decided gap
          this change does not close, since `@xyflow/react`'s theming has no
          token bridge in this codebase.
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

export function TreeCanvas({ rootPersonId }: { rootPersonId?: string }) {
  return (
    <ReactFlowProvider>
      <TreeFlowInner rootPersonId={rootPersonId} />
    </ReactFlowProvider>
  )
}
