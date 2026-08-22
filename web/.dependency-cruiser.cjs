/**
 * Frontend layer boundaries — the counterpart of the backend's import-linter
 * ratchet (ADR-013). A violation is a CI failure, not something to catch in review.
 *
 * Legacy trees (src/lib/api, src/lib/hooks, src/application, src/infrastructure)
 * are excluded: they are being deleted slice by slice, and failing on them now
 * would only teach people to disable the tool.
 */
const LEGACY = '^src/(lib/(api|hooks)|application|infrastructure|types)/'

module.exports = {
  forbidden: [
    {
      name: 'domain-is-pure',
      comment:
        'src/domain must stay framework-agnostic — it is the layer web and mobile ' +
        'agree on conceptually, and the only layer that is trivially testable.',
      severity: 'error',
      from: { path: '^src/domain/' },
      to: {
        dependencyTypes: ['npm', 'npm-dev', 'npm-peer'],
        pathNot: '^(typescript|@types/)',
      },
    },
    {
      name: 'domain-imports-only-domain',
      severity: 'error',
      from: { path: '^src/domain/' },
      to: { path: '^src/', pathNot: '^src/domain/' },
    },
    {
      name: 'api-layer-has-no-react',
      comment:
        'Transport must not reach for React — it runs in RSC and in tests too. ' +
        "`to.path` matches a dependency's *resolved* file path, never the bare " +
        'import specifier (dependency-cruiser, src/validate/matchers.mjs, ' +
        '`matchesToPath`), so an anchored `^react$` never matches a real resolved ' +
        'path — not "node_modules/react/index.js" under plain npm, and even less ' +
        'so "node_modules/.pnpm/react@19.x/node_modules/react/index.js" under ' +
        "pnpm's isolated store. That was this rule's shape before seed S-029 " +
        'measured it: `pnpm depcruise` reported zero violations for a throwaway ' +
        "`import { useState } from 'react'` planted in `features/persons/api/`, " +
        "confirmed by dependency-cruiser's own JSON output marking that edge " +
        '`"valid": true`. The pattern below matches the last `node_modules/<pkg>/` ' +
        'segment instead, which every resolver (npm, yarn, pnpm) produces ' +
        'regardless of what sits in front of it.',
      severity: 'error',
      from: { path: '^src/features/[^/]+/api/' },
      to: {
        path: 'node_modules/(react|react-dom|@tanstack/react-query)/',
        dependencyTypes: ['npm'],
      },
    },
    {
      name: 'ui-does-not-call-transport',
      comment: 'Components go through hooks or model, never straight to a repository.',
      severity: 'error',
      from: { path: '^src/features/([^/]+)/ui/' },
      to: { path: '^src/features/$1/api/' },
    },
    {
      name: 'cross-feature-only-via-index',
      comment:
        'Import a sibling feature through its index.ts. Reaching into another ' +
        "feature's internals is what turns slices back into a ball of mud.",
      severity: 'error',
      from: { path: '^src/features/([^/]+)/' },
      to: {
        path: '^src/features/(?!$1/)[^/]+/.+',
        pathNot: '^src/features/[^/]+/index\\.ts$',
      },
    },
    {
      name: 'app-does-not-call-transport',
      severity: 'error',
      from: { path: '^src/app/' },
      to: { path: '^src/features/[^/]+/api/' },
    },
    {
      name: 'nothing-imports-app',
      comment: 'src/app is the entry point; it is imported by the framework only.',
      severity: 'error',
      from: { pathNot: '^src/app/' },
      to: { path: '^src/app/' },
    },
    {
      name: 'no-circular',
      severity: 'error',
      from: {},
      to: { circular: true },
    },
    {
      name: 'no-orphans',
      severity: 'warn',
      from: {
        orphan: true,
        pathNot: [
          '\\.d\\.ts$',
          '^src/app/',
          '^src/generated/',
          '(^|/)(instrumentation|middleware)\\.ts$',
        ],
      },
      to: {},
    },
  ],
  options: {
    doNotFollow: { path: 'node_modules' },
    exclude: { path: [LEGACY, '\\.test\\.tsx?$', '^src/generated/'] },
    tsPreCompilationDeps: true,
    tsConfig: { fileName: 'tsconfig.json' },
    enhancedResolveOptions: { exportsFields: ['exports'], conditionNames: ['import', 'require'] },
    reporterOptions: { text: { highlightFocused: true } },
  },
}
