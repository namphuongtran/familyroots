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
        <MiniMap
          nodeColor={(n) =>
            n.data?.gender === 'male'
              ? '#93c5fd'
              : n.data?.gender === 'female'
                ? '#f9a8d4'
                : '#d1d5db'
          }
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
