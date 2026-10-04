/**
 * Frontend layer boundaries — the counterpart of the backend's import-linter
 * ratchet (ADR-013). A violation is a CI failure, not something to catch in review.
 *
 * The legacy trees (the web architecture spec's § 3.2 list, `LEGACY` below) are in
 * the graph, cruised like everything else, so an import out of legacy is a real
 * edge and a module only legacy imports is not an orphan. No rule but
 * `nothing-imports-legacy` takes a legacy module as its subject: every rule whose
 * `from` could match a legacy path names `LEGACY` in `pathNot`, and `no-circular`
 * also skips an edge that ends inside legacy. A new rule with a broad `from` needs
 * the same. Legacy is being deleted slice by slice (ADR-060), not refactored into
 * compliance.
 *
 * `nothing-imports-legacy` is a ratchet. Today's violations sit in
 * `.dependency-cruiser-known-violations.json`, which `pnpm depcruise` reads through
 * `--ignore-known`, and `pnpm depcruise:ratchet` fails a pull request that adds an
 * entry to it (ADR-060 § 4, issue #171). See web/CLAUDE.md, "Migration notes".
 */
const LEGACY =
  '^src/(lib/(api|hooks|types)|application|infrastructure|types|' +
  'components/(admin|auth|backoffice|documents|events|family-tree|members))/'

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
        "pnpm's isolated store. That was this rule's shape before it was fixed " +
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
      from: { pathNot: ['^src/app/', LEGACY] },
      to: { path: '^src/app/' },
    },
    {
      name: 'nothing-imports-legacy',
      comment:
        'The legacy trees are frozen, not extended (ADR-060 § 4). A legacy module may ' +
        'import another; nothing else may import one. The imports that already exist are ' +
        'the baseline, and it may only shrink: delete or re-point the import, then run ' +
        '`pnpm depcruise:baseline`.',
      severity: 'error',
      from: { pathNot: LEGACY },
      to: { path: LEGACY },
    },
    {
      name: 'no-circular',
      comment:
        'An edge with an end inside legacy is never reported, so a cycle wholly inside ' +
        'legacy is silent. A cycle that passes through legacy is still reported on its ' +
        'edges outside legacy. Filtering on the cycle instead (`viaOnly`) would hide real ' +
        'ones: dependency-cruiser records only the first cycle its search finds for an ' +
        'edge (`getCycle`, src/graph-utl/indexed-module-graph.mjs), and that can be a ' +
        'route through legacy when one outside it also exists.',
      severity: 'error',
      from: { pathNot: LEGACY },
      to: { circular: true, pathNot: LEGACY },
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
          LEGACY,
        ],
      },
      to: {},
    },
  ],
  options: {
    doNotFollow: { path: 'node_modules' },
    exclude: { path: ['\\.test\\.tsx?$', '^src/generated/'] },
    tsPreCompilationDeps: true,
    tsConfig: { fileName: 'tsconfig.json' },
    enhancedResolveOptions: { exportsFields: ['exports'], conditionNames: ['import', 'require'] },
    reporterOptions: { text: { highlightFocused: true } },
  },
}
