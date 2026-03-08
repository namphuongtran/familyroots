import { z } from 'zod'

const parentChildTypes = ['biological', 'adopted', 'step', 'foster'] as const
const marriageStatuses = ['married', 'divorced', 'widowed', 'separated'] as const

export const marriageSchema = z
  .object({
    person1_id: z.string().uuid('ID người thứ nhất không hợp lệ'),
    person2_id: z.string().uuid('ID người thứ hai không hợp lệ'),
    status: z.enum(marriageStatuses).default('married'),
    marriage_date: z.string().optional(),
    divorce_date: z.string().optional(),
    marriage_place: z.string().max(255).optional(),
    spouse_order: z.number().int().min(1).optional(),
    notes: z.string().max(1000).optional(),
  })
  .refine(
    (d) => d.person1_id !== d.person2_id,
    { message: 'Không thể tạo hôn nhân với chính mình', path: ['person2_id'] },
  )

export type MarriageFormValues = z.infer<typeof marriageSchema>

export const marriageDefaultValues: Partial<MarriageFormValues> = {
  status: 'married',
}

export const parentChildSchema = z
  .object({
    parent_id: z.string().uuid('ID cha/mẹ không hợp lệ'),
    child_id: z.string().uuid('ID con không hợp lệ'),
    relationship_type: z.enum(parentChildTypes).default('biological'),
    notes: z.string().max(1000).optional(),
  })
  .refine(
    (d) => d.parent_id !== d.child_id,
    { message: 'Cha/mẹ và con không thể là cùng một người', path: ['child_id'] },
  )

export type ParentChildFormValues = z.infer<typeof parentChildSchema>

export const parentChildDefaultValues: Partial<ParentChildFormValues> = {
  relationship_type: 'biological',
}
