import type {
  MarriageCommandRepository,
  ParentChildCommandRepository,
} from '@/application/relationships/ports/relationship-command-repository'
import type {
  Marriage,
  MarriageCreateInput,
  MarriageUpdateInput,
  ParentChild,
  ParentChildCreateInput,
  ParentChildUpdateInput,
} from '@/lib/types'
import { marriagesApi, parentChildApi } from '@/lib/api/relationships'

export class HttpMarriageCommandRepository implements MarriageCommandRepository {
  async create(input: MarriageCreateInput): Promise<Marriage> {
    return marriagesApi.create(input)
  }

  async update(id: string, input: MarriageUpdateInput): Promise<Marriage> {
    return marriagesApi.update(id, input)
  }

  async delete(id: string): Promise<void> {
    await marriagesApi.delete(id)
  }
}

export class HttpParentChildCommandRepository implements ParentChildCommandRepository {
  async create(input: ParentChildCreateInput): Promise<ParentChild> {
    return parentChildApi.create(input)
  }

  async update(id: string, input: ParentChildUpdateInput): Promise<ParentChild> {
    return parentChildApi.update(id, input)
  }

  async delete(id: string): Promise<void> {
    await parentChildApi.delete(id)
  }
}

export const marriageCommandRepository = new HttpMarriageCommandRepository()
export const parentChildCommandRepository = new HttpParentChildCommandRepository()
