# web

## Responsibility
Provides the browser UX, admin dashboards, and backoffice workflows. It acts as a client over the backend API and does NOT own any persistent data itself.

## Stack
Next.js 16, React 19, TypeScript, TailwindCSS, Zustand (State), XYFlow (Tree Visualization)

## Domain Model
Maps backend contracts to local TypeScript interfaces (e.g., `Person`, `TreeNode`).

## API Surface
Exposes internal Next.js routes, but primarily consumes the `backend` REST API.

## Event Contracts
None. Pull-based client.

## Data Ownership
None.

## Key Commands
- dev: `make web-dev`
- build: `make web-build`
- lint: `make web-lint`
- type-check: `make web-type-check`

## Error Handling Pattern
Catches structured backend errors and maps them to toast notifications or inline form errors.

## Don't Do
- Do not duplicate business logic; rely on the backend API.
- Do not mutate state without updating Zustand and revalidating queries.

## Known Issues
- Web testing harness appears less complete than backend/mobile test posture.