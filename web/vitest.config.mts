import { defineConfig } from 'vitest/config'

// Two projects, split by file extension:
//   *.test.ts  → node, for domain and transport logic (fast, no DOM)
//   *.test.tsx → jsdom, for hooks and components
// Tests live next to the code they cover so a slice stays self-contained.
export default defineConfig({
  // Vite 8 reads tsconfig `paths` itself — this is what maps `@/*` to `./src/*`.
  resolve: { tsconfigPaths: true },
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: 'unit',
          environment: 'node',
          include: ['src/**/*.test.ts'],
        },
      },
    ],
  },
})
