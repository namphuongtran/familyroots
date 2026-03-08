import { z } from 'zod'

export const memberSchema = z
  .object({
    full_name: z.string().min(1, 'Họ và tên là bắt buộc').max(255),
    birth_name: z.string().max(255).optional(),
    courtesy_name: z.string().max(255).optional(),
    gender: z.enum(['male', 'female', 'unknown']),
    birth_date: z.string().optional(),
    birth_date_approx: z.boolean(),
    death_date: z.string().optional(),
    death_date_approx: z.boolean(),
    birth_place: z.string().max(255).optional(),
    death_place: z.string().max(255).optional(),
    residence_place: z.string().max(255).optional(),
    generation: z.number().int().min(1).max(999).optional(),
    is_clan_founder: z.boolean(),
    is_clan_member: z.boolean(),
    biography: z.string().optional(),
    avatar_url: z.string().url('URL không hợp lệ').optional().or(z.literal('')),
    notes: z.string().optional(),
  })
  .refine(
    (d) => {
      if (d.birth_date && d.death_date) {
        return new Date(d.birth_date) <= new Date(d.death_date)
      }
      return true
    },
    { message: 'Ngày mất phải sau ngày sinh', path: ['death_date'] },
  )

export type MemberFormValues = z.infer<typeof memberSchema>

export const memberDefaultValues: MemberFormValues = {
  full_name: '',
  gender: 'unknown',
  birth_date_approx: false,
  death_date_approx: false,
  is_clan_founder: false,
  is_clan_member: true,
}
