import { memo } from 'react'
import type { EdgeProps } from '@xyflow/react'

/** A double horizontal line between a member and a spouse. */
export const SpouseEdge = memo(function SpouseEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
}: EdgeProps) {
  const midY = (sourceY + targetY) / 2

  return (
    <>
      <path
        id={`${id}-top`}
        d={`M ${sourceX},${midY - 3} L ${targetX},${midY - 3}`}
        stroke="#D4AF37"
        strokeWidth={1.5}
        fill="none"
      />
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
