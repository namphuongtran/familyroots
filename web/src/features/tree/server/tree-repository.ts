/**
 * The `tree` repository: fetch (`../api/tree-api`) → parse (`../model/tree-dto`) → map to
 * `@/domain/tree/tree`. Returns domain values only.
 */

import type { FamilyTree, FocusView } from '@/domain/tree/tree'
import { unwrapData } from '@/shared/http/envelope'
import * as api from '../api/tree-api'
import type { GetFocusQuery, GetTreeQuery, TreeApiCallOptions } from '../api/tree-api'
import {
  focusViewDtoSchema,
  toFamilyTree,
  toFocusView,
  treeResponseDtoSchema,
} from '../model/tree-dto'

export type { GetFocusQuery, GetTreeQuery, TreeApiCallOptions }

export async function getTree(
  query: GetTreeQuery,
  options: TreeApiCallOptions,
): Promise<FamilyTree> {
  const body = await api.getTree(query, options)
  return unwrapData(body, (raw) => toFamilyTree(treeResponseDtoSchema.parse(raw)))
}

export async function getFocus(
  personId: string,
  query: GetFocusQuery,
  options: TreeApiCallOptions,
): Promise<FocusView> {
  const body = await api.getFocus(personId, query, options)
  return unwrapData(body, (raw) => toFocusView(focusViewDtoSchema.parse(raw)))
}
