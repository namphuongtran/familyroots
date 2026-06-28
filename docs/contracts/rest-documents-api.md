# Contract: documents-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/documents

Core operations:
- POST /
- GET /  (cursor-paginated; query params: cursor, limit, person_id, document_type, fields)
- GET /{id}
- DELETE /{id}  (admin)
- PATCH /{id}/set-avatar

List response envelope (cursor pagination):
```
{
  "data": [ ... ],
  "meta": { "cursor": "<base64|null>", "has_more": true, "limit": 20 }
}
```
- `meta.cursor` is null on the last page; pass it back as `?cursor=` to fetch the next.

Upload expectations:
- multipart/form-data upload
- file, title, document_type required
- person_id, description, taken_date, taken_place optional
- supports approved media and document MIME types

## Versioning & Compatibility Rules
- Adding optional metadata fields is non-breaking.
- Changing upload requirements or allowed MIME sets is breaking.
- Keep presigned URL and delete semantics stable.
