import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  resolve: { tsconfigPaths: true },
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: 'unit',
          environment: 'node',
          // messages/**: seed S-062's locale key-set parity test. It lives outside src/ on
          // purpose (S-038 sweeps web/src the same batch), so the include glob was widened
          // rather than moving the test under src/. See messages/message-key-parity.test.ts.
          // e2e/**/*.guard.test.ts: seed S-070's fence. It scans web/src for any sign that
          // shipped code has learned the authenticated e2e harness exists, so it is a unit
          // test about src/ that lives beside the harness it protects. The `.guard.` infix
          // keeps Playwright from claiming it — see playwright.config.ts's AUTH_SPECS.
          include: ['src/**/*.test.ts', 'messages/**/*.test.ts', 'e2e/**/*.guard.test.ts'],
        },
      },
      {
        extends: true,
        plugins: [react()],
        test: {
          name: 'component',
          environment: 'jsdom',
          include: ['src/**/*.test.tsx'],
          setupFiles: ['./vitest.setup.ts'],
        },
      },
    ],
  },
})
