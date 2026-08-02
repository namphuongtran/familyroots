# Generated API types

`api-types.ts` is generated from the backend's `/openapi.json` by `pnpm gen:api`.
Never edit it by hand — CI regenerates it and fails on any diff.

Feature slices do not import this file directly. They import it in their
`api/*.dto.ts`, where a hand-written Zod schema parses the subset the frontend
actually consumes, and the generated type is used to prove that subset is
compatible with the real wire shape.

Two things the generator cannot express, which the Zod schema must:

- **Nullability and optionality are both real.** `HistoricalDate` generates as
  `{date?: string | null; precision: string; display?: string | null; lunar?: string | null}`.
  A mapper has to normalise "key absent" and "key null" to the same domain value.
- **Pattern-constrained strings widen.** `precision` is a regex in the schema, so
  it generates as `string`, not the five-way union. The Zod schema is the only
  place that narrowing happens — do not cast.
