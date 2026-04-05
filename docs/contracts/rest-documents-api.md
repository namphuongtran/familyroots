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
- GET /
- GET /{id}
- DELETE /{id}
- PATCH /{id}/set-avatar

Upload expectations:
- multipart/form-data upload
- file, title, document_type required
- person_id, description, taken_date, taken_place optional
- supports approved media and document MIME types

## Versioning & Compatibility Rules
- Adding optional metadata fields is non-breaking.
- Changing upload requirements or allowed MIME sets is breaking.
- Keep presigned URL and delete semantics stable.
