#!/usr/bin/env node
/**
 * Regenerate src/generated/api-types.ts from the backend's OpenAPI schema.
 *
 * CI runs this and then `git diff --exit-code src/generated`, so a backend shape
 * change that the frontend has not absorbed fails the build instead of breaking
 * at runtime (risk R3).
 *
 * Two sources, same output (verified byte-identical):
 *
 *   pnpm gen:api                       # from a running backend, the dev default
 *   pnpm gen:api path/to/openapi.json  # from a schema file, what CI uses
 *
 * The file form exists because FastAPI can print the document without a server
 * or a database:
 *
 *   cd backend && uv run python -c \
 *     "import json;from app.main import create_app;print(json.dumps(create_app().openapi()))" \
 *     > /tmp/openapi.json
 *
 * The header records the *logical* source, not the transient path, so the two
 * routes produce the same committed file.
 */
import { access, writeFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import { fileURLToPath } from 'node:url'
import openapiTS, { astToString } from 'openapi-typescript'

const ORIGIN = process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'
const OUTPUT = fileURLToPath(new URL('../src/generated/api-types.ts', import.meta.url))

const HEADER = `/**
 * GENERATED FILE — DO NOT EDIT BY HAND.
 * Source: the backend OpenAPI document (/openapi.json)
 * Regenerate with: pnpm gen:api
 */

`

async function resolveSource() {
  const fileArg = process.argv[2]
  if (fileArg === undefined) return { schema: new URL(`${ORIGIN}/openapi.json`), label: ORIGIN }
  try {
    await access(fileArg)
  } catch {
    console.error(`Schema file not found: ${fileArg}`)
    process.exit(1)
  }
  return { schema: pathToFileURL(fileArg), label: fileArg }
}

async function main() {
  const { schema, label } = await resolveSource()

  let ast
  try {
    ast = await openapiTS(schema)
  } catch (error) {
    console.error(
      `Could not read the OpenAPI schema from ${label}.\n` +
        `  Running backend:  cd backend && uv run uvicorn app.main:app\n` +
        `  Or pass a file:   pnpm gen:api /tmp/openapi.json\n`,
    )
    console.error(error)
    process.exit(1)
  }

  await writeFile(OUTPUT, HEADER + astToString(ast), 'utf8')
  console.log(`Wrote ${OUTPUT} from ${label}`)
}

await main()
