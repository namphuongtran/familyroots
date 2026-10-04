/**
 * The one place the auth slice's query keys are built.
 *
 * **The session has one key, and that is the whole fix for the dashboard runaway.** Every
 * consumer reads this cache entry, so the number of `GET /auth/me` a page load sends does not
 * grow with the number of components that ask (`web/CLAUDE.md`, "The `(dashboard)` group runs
 * away"; `e2e/auth/dashboard.auth.spec.ts` counts it). The key carries no clan id on purpose:
 * the session says who is signed in, never which clan they act in (`CONTEXT.md`, **Session**),
 * so a clan switch must not refetch it.
 */
export const authKeys = {
  all: ['auth'] as const,
  session: () => ['auth', 'session'] as const,
}
