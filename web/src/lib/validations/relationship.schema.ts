import { z } from 'zod'

const parentChildSubtypes = ['biological', 'adoptive', 'step', 'foster'] as const
const spouseSubtypes = ['married', 'divorced', 'widowed', 'partner'] as const

export const relationshipSchema = z
  .object({
    member_id: z.string().uuid('ID thành viên không hợp lệ'),
    related_id: z.string().uuid('ID thành viên liên quan không hợp lệ'),
    relation_type: z.enum(['parent', 'child', 'spouse']),
    relation_subtype: z.enum([
      ...parentChildSubtypes,
      ...spouseSubtypes,
    ] as [string, ...string[]]),
    start_date: z.string().optional(),
    end_date: z.string().optional(),
    is_primary: z.boolean(),
    notes: z.string().max(1000).optional(),
  })
  .refine(
    (d) => d.member_id !== d.related_id,
    { message: 'Không thể tạo quan hệ với chính mình', path: ['related_id'] },
  )
  .refine(
    (d) => {
      if (d.relation_type === 'spouse') {
        return spouseSubtypes.includes(d.relation_subtype as typeof spouseSubtypes[number])
      }
      return parentChildSubtypes.includes(d.relation_subtype as typeof parentChildSubtypes[number])
    },
    { message: 'Kiểu quan hệ không phù hợp với loại quan hệ', path: ['relation_subtype'] },
  )

export type RelationshipFormValues = z.infer<typeof relationshipSchema>

export const relationshipDefaultValues: Partial<RelationshipFormValues> = {
  relation_type: 'child',
  relation_subtype: 'biological',
  is_primary: true,
}
