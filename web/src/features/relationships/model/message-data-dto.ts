/**
 * The `{"data": {"message": ..., "id": ...}}` body a `DELETE` returns.
 * Mirrors `components.schemas.MessageData`, same duplication story as
 * `historical-date-dto.ts`: `persons` has its own copy, and the duplication
 * will be extracted to `shared/` when the next slice after this one needs it.
 */

import { z } from 'zod'
import type { components } from '@/generated/api-types'
import type { RelationshipActionResult } from '@/domain/relationship/relationship'

export const messageDataDtoSchema = z.object({
  message: z.string(),
  id: z.string().nullable().optional(),
})

export type MessageDataDto = z.infer<typeof messageDataDtoSchema>

export function assertMessageDataDtoMatchesGenerated(
  dto: MessageDataDto,
): components['schemas']['MessageData'] {
  return dto
}

export function toRelationshipActionResult(dto: MessageDataDto): RelationshipActionResult {
  return { message: dto.message, id: dto.id ?? null }
}
