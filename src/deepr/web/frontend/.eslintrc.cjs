/**
 * ESLint config (legacy format - eslint 8.x).
 *
 * This file was missing entirely: `npm run lint` failed with "couldn't find
 * a configuration file" on every run, so frontend lint has never gated
 * anything. Standard Vite react-ts ruleset; @typescript-eslint 8.x supports
 * eslint ^8.57 with legacy config.
 */
module.exports = {
  root: true,
  env: { browser: true, es2021: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', 'node_modules', '.eslintrc.cjs', 'screenshot-qa.mjs'],
  parser: '@typescript-eslint/parser',
  plugins: ['react-refresh'],
  rules: {
    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    // Pragmatic baseline for an existing codebase: surface real problems
    // without turning the first lint run into a 500-error cleanup project.
    '@typescript-eslint/no-explicit-any': 'off',
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
  },
  overrides: [
    {
      // shadcn/ui primitives export cva variants alongside components by
      // design; fast-refresh granularity is irrelevant for these files.
      files: ['src/components/ui/**/*.tsx'],
      rules: { 'react-refresh/only-export-components': 'off' },
    },
  ],
}
