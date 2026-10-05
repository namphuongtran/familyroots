/**
 * The server-only half of the `auth` slice's public surface: the guard (#186, ADR-061 § 3-5).
 *
 * It is a second entry, not a line in `index.ts`, because `server/guard.ts` imports
 * `server-only` and `next/headers`, and `index.ts` is imported by client components (`Header`,
 * `Sidebar`, the auth screens). One barrel holding both would pull the guard into every client
 * bundle, where `server-only` throws on import. `context.server.ts` and `context.client.ts` in
 * `shared/http` split the same way.
 *
 * Only `src/app/**` imports it: a layout or a page names what it needs, and the guard admits or
 * redirects. Other features reach the slice through `index.ts` alone
 * (`cross-feature-only-via-index`).
 */

export type { ClanRoute, PlatformRoute } from './server/guard'
export { guardClanRoute, guardPlatformRoute } from './server/guard'
