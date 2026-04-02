import type {
  Marriage,
  MarriageCreateInput,
  MarriageUpdateInput,
  ParentChild,
  ParentChildCreateInput,
  ParentChildUpdateInput,
} from '@/lib/types'

export interface MarriageCommandRepository {
  create(input: MarriageCreateInput): Promise<Marriage>
  update(id: string, input: MarriageUpdateInput): Promise<Marriage>
  delete(id: string): Promise<void>
}

export interface ParentChildCommandRepository {
  create(input: ParentChildCreateInput): Promise<ParentChild>
  update(id: string, input: ParentChildUpdateInput): Promise<ParentChild>
  delete(id: string): Promise<void>
}