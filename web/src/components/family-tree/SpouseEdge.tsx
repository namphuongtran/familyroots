import { memo } from 'react'
import { BaseEdge, type EdgeProps, getStraightPath } from '@xyflow/react'

// Renders a double horizontal line to indicate a marriage / spouse relationship
export const SpouseEdge = memo(function SpouseEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  style,
  markerEnd,
}: EdgeProps) {
  const [edgePath] = getStraightPath({ sourceX, sourceY, targetX, targetY })
  const midY = (sourceY + targetY) / 2

  return (
    <>
      {/* top line */}
      <path
        id={`${id}-top`}
        d={`M ${sourceX},${midY - 3} L ${targetX},${midY - 3}`}
        stroke="#D4AF37"
        strokeWidth={1.5}
        fill="none"
      />
      {/* bottom line */}
      <path
        id={`${id}-bottom`}
        d={`M ${sourceX},${midY + 3} L ${targetX},${midY + 3}`}
        stroke="#D4AF37"
        strokeWidth={1.5}
        fill="none"
      />
    </>
  )
})
