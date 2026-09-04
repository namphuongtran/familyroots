// Barrel export for all types
export type {
  ApiResponse,
  CursorPage,
  ApiError,
  TreeApiResponse,
  TreeAncestorsResponse,
  ClanSwitchResponse,
  UserProfile,
  UserClanMembership,
  UserClansResponse,
} from './api'
// the legacy-component deletion trimmed this re-export to `Person` and `PersonSummary`, the two
// types `./member` still declares. See that file's own header comment for
// why each removed type's last reader went with it.
export type { Person, PersonSummary } from './member'
export type {
  Marriage,
  MarriageStatus,
  MarriageCreateInput,
  MarriageUpdateInput,
  ParentChild,
  ParentChildType,
  ParentChildCreateInput,
  ParentChildUpdateInput,
} from './relationship'
export type { TreeNode, SpouseNode, PathStep, RelationshipPath } from './tree'
export type {
  ClanEvent,
  UpcomingEvent,
  EventType,
  EventCreateInput,
  EventUpdateInput,
} from './event'
export type {
  DocumentResponse,
  DocumentSummary,
  DocumentUploadMeta,
  DocumentType,
} from './document'
export type {
  ClanRole,
  ClanUserMembership,
  ClanSettings,
  PlatformClanSummary,
  PlatformMetrics,
} from './admin'
