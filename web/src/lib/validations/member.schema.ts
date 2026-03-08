import { z } from 'zod'

export const personSchema = z
  .object({
    full_name: z.string().min(1, 'Họ và tên là bắt buộc').max(255),
    birth_name: z.string().max(255).optional(),
    courtesy_name: z.string().max(255).optional(),
    posthumous_name: z.string().max(255).optional(),
    alias_name: z.string().max(255).optional(),
    gender: z.enum(['male', 'female', 'unknown']),
    birth_date: z.string().optional(),
    birth_date_lunar: z.string().max(30).optional(),
    birth_date_approx: z.boolean(),
    death_date: z.string().optional(),
    death_date_lunar: z.string().max(30).optional(),
    death_date_approx: z.boolean(),
    birth_place: z.string().max(255).optional(),
    death_place: z.string().max(255).optional(),
    burial_place: z.string().max(255).optional(),
    tomb_location: z.string().max(255).optional(),
    residence_place: z.string().max(255).optional(),
    religion: z.string().max(100).optional(),
    nationality: z.string().max(100).optional(),
    occupation: z.string().max(255).optional(),
    education_level: z.string().max(255).optional(),
    title_rank: z.string().max(255).optional(),
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

export type PersonFormValues = z.infer<typeof personSchema>

export const personDefaultValues: PersonFormValues = {
  full_name: '',
  gender: 'unknown',
  birth_date_approx: false,
  death_date_approx: false,
}
