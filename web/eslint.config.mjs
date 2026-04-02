import nextConfig from 'eslint-config-next'

const config = [
  ...nextConfig,
  {
    files: ['src/domain/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            '@/app/*',
            '@/components/*',
            '@/lib/api/*',
            '@/lib/hooks/*',
            '@/store/*',
            '@/infrastructure/*',
            '@tanstack/*',
            'next/*',
            'react*',
            'axios',
            '@supabase/*',
          ],
        },
      ],
    },
  },
  {
    files: ['src/application/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            '@/app/*',
            '@/components/*',
            '@/lib/api/*',
            '@/lib/hooks/*',
            '@/store/*',
            '@/infrastructure/*',
            'next/*',
            'react*',
            'axios',
            '@supabase/*',
          ],
        },
      ],
    },
  },
]

export default config
