'use client'

import {
  useMemo,
  useRef,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
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
  /** A node held down (touch long-press, or a right click): the node's action sheet. */
  onLongPressPerson?: (personId: string) => void
}

/** How long a press must last to count as a long-press. */
const LONG_PRESS_MS = 500
/** A press that travels further than this is a pan, not a long-press. */
const LONG_PRESS_SLOP_PX = 10

function personIdAt(target: EventTarget | null): string | null {
  if (!(target instanceof Element)) return null
  return target.closest<HTMLElement>('[data-person-id]')?.dataset.personId ?? null
}

/**
 * Spec §3.5's "tree node long-press sheet". XYFlow has no long-press event, so the canvas times
 * a held pointer itself, and cancels on release or on a move past the slop (a pan). A right
 * click opens the same sheet, which is also what Android's long-press fires.
 */
function useLongPress(onLongPress: ((personId: string) => void) | undefined) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const start = useRef<{ x: number; y: number } | null>(null)

  function cancel() {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
    start.current = null
  }

  return {
    onPointerDown(event: ReactPointerEvent) {
      cancel()
      const personId = personIdAt(event.target)
      if (!onLongPress || !personId) return
      start.current = { x: event.clientX, y: event.clientY }
      timer.current = setTimeout(() => {
        cancel()
        onLongPress(personId)
      }, LONG_PRESS_MS)
    },
    onPointerMove(event: ReactPointerEvent) {
      if (!start.current) return
      const dx = event.clientX - start.current.x
      const dy = event.clientY - start.current.y
      if (Math.hypot(dx, dy) > LONG_PRESS_SLOP_PX) cancel()
    },
    onPointerUp: cancel,
    onPointerCancel: cancel,
    onPointerLeave: cancel,
    onContextMenu(event: ReactMouseEvent) {
      const personId = personIdAt(event.target)
      if (!onLongPress || !personId) return
      event.preventDefault()
      cancel()
      onLongPress(personId)
    },
  }
}

/**
 * The XYFlow canvas over an already-loaded tree. Nodes are derived from the tree on every
 * render rather than held in `useNodesState`: the legacy canvas seeded that state on its first
 * render, while the query was still loading, and so never received the nodes.
 */
function TreeFlow({ root, selectedPersonId, onSelectPerson, onLongPressPerson }: TreeCanvasProps) {
  const longPress = useLongPress(onLongPressPerson)
  const { nodes, edges } = useMemo(
    () => treeToFlow(root, selectedPersonId),
    [root, selectedPersonId],
  )

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    onSelectPerson((node.data as PersonNodeData).personId)
  }

  return (
    <div className="relative h-full w-full" {...longPress}>
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
