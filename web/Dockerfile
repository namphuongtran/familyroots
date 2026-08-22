# ── Stage 1: Base image with pnpm ─────────────────────────────────────────────
FROM node:22-alpine AS base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

# ── Stage 2: Install ALL dependencies (incl. devDeps needed for build) ─────────
FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# ── Stage 3: Build the Next.js application ─────────────────────────────────────
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1

# S-071: Next.js inlines every `NEXT_PUBLIC_*` value into the browser bundle during
# `pnpm build`, not at container run time. Passing these two only through `environment:`
# in docker-compose.yml (run time) bakes `undefined` into the client bundle, and
# `SupabaseSetupNotice.tsx` — a Client Component that reads both — renders the
# "Supabase is not configured" banner regardless of what the container is later given.
# So they must arrive here, as build arguments, promoted to env vars for `pnpm build`
# to inline. Do NOT add `NEXT_PUBLIC_API_URL` or any other NEXT_PUBLIC_* here unless a
# client component actually reads it — check before adding one (see the seed's own
# "Out of scope").
#
# THIS MAKES THE IMAGE ENVIRONMENT-SPECIFIC. An image built with staging's Supabase
# project has staging's URL and anon key permanently baked into its JS bundle — it
# cannot be promoted to production unchanged. Build a fresh image per environment,
# passing that environment's own values as --build-arg (or docker-compose.yml's
# `build.args`, which reads them from the same `.env` the run-time `environment:`
# block below already uses).
#
# S-071's seed text said `middleware.ts` and `/api/auth/callback/route.ts` "run
# server-side and read the run-time environment correctly today" and should not get
# build args of their own. **Measured 2026-08-22, and that half is false**: both files
# read `process.env.NEXT_PUBLIC_SUPABASE_URL`/`_ANON_KEY` too, and Next's inlining is not
# scoped to Client Components — it statically replaces `process.env.NEXT_PUBLIC_*`
# wherever the bundler sees it, middleware and route handlers included. Built one image
# with these two ARGs left empty, ran it twice with two different runtime values on the
# same env var names, and hit a protected route and the callback route in each: every
# probe read back the empty build-time value, never the container's own runtime value
# (throwaway `console.error` in each file, reverted before commit — not in this diff).
# No separate ARG was added for either file: it is not achievable anyway, since the
# bundler inlines by variable name across the whole build graph, so the ARGs above
# already supply whatever value middleware and the callback route get baked with. This
# is not a new leak — `NEXT_PUBLIC_SUPABASE_ANON_KEY` is Supabase's own public/anon
# key, meant to ship in a client bundle — but it does mean the image was *already*
# fully baked before this seed, just baked to empty, and middleware's session check was
# never live in this image (`if (!supabaseUrl || !supabaseKey) return intlResponse`
# always took the skip branch). Fixing the client half here fixes that too, for the same
# reason. Do not read this as license to bake `SUPABASE_SERVICE_ROLE_KEY` the same way —
# that name has no `NEXT_PUBLIC_` prefix, is never read by web/, and stays backend-only.
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ENV NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL}
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=${NEXT_PUBLIC_SUPABASE_ANON_KEY}

RUN pnpm build

# ── Stage 4: Production runner (minimal image) ─────────────────────────────────
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
