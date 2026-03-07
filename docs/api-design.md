# API Design

## Base URL

```
/api/v1/
```

## Authentication

All endpoints (except login/register) require a Bearer JWT token.

```
Authorization: Bearer <access_token>
```

## Endpoints

> TODO: implement in Prompt 2 — detailed endpoint specifications

### Auth (`/api/v1/auth/`)

| Method | Path         | Description           |
|--------|--------------|-----------------------|
| POST   | `/register`  | Register new user     |
| POST   | `/login`     | Login, return JWT     |
| POST   | `/refresh`   | Refresh access token  |
| POST   | `/logout`    | Invalidate token      |

### Members (`/api/v1/members/`)

| Method | Path         | Description              |
|--------|--------------|--------------------------|
| GET    | `/`          | List clan members        |
| POST   | `/`          | Create member            |
| GET    | `/{id}`      | Get member detail        |
| PUT    | `/{id}`      | Update member            |
| DELETE | `/{id}`      | Delete member            |

### Relationships (`/api/v1/relationships/`)

| Method | Path         | Description              |
|--------|--------------|--------------------------|
| GET    | `/`          | List relationships       |
| POST   | `/`          | Create relationship      |
| DELETE | `/{id}`      | Remove relationship      |

### Documents (`/api/v1/documents/`)

| Method | Path         | Description              |
|--------|--------------|--------------------------|
| GET    | `/`          | List documents           |
| POST   | `/`          | Upload document          |
| GET    | `/{id}`      | Get document             |
| DELETE | `/{id}`      | Delete document          |

### Events (`/api/v1/events/`)

| Method | Path         | Description              |
|--------|--------------|--------------------------|
| GET    | `/`          | List clan events         |
| POST   | `/`          | Create event             |
| GET    | `/{id}`      | Get event detail         |
| PUT    | `/{id}`      | Update event             |
| DELETE | `/{id}`      | Delete event             |

### Tree (`/api/v1/tree/`)

| Method | Path         | Description              |
|--------|--------------|--------------------------|
| GET    | `/`          | Get full family tree     |
| GET    | `/{id}`      | Get subtree for member   |

### Clans (`/api/v1/clans/`)

| Method | Path         | Description              |
|--------|--------------|--------------------------|
| GET    | `/`          | List clans (admin)       |
| POST   | `/`          | Create clan              |
| GET    | `/{id}`      | Get clan detail          |
| PUT    | `/{id}`      | Update clan settings     |

### Notifications (`/api/v1/notifications/`)

| Method | Path         | Description              |
|--------|--------------|--------------------------|
| GET    | `/`          | List notifications       |
| PUT    | `/{id}/read` | Mark as read             |

## Error Response Format

```json
{
  "detail": "Error message",
  "code": "ERROR_CODE",
  "status_code": 400
}
```

## Pagination

```
GET /api/v1/members/?page=1&page_size=20
```

Response includes pagination metadata:

```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "pages": 5
}
```
