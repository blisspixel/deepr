import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeSanitize from 'rehype-sanitize'
import rehypeKatex from 'rehype-katex'
import katex from 'katex'

const require = createRequire(import.meta.url)
const typographyUtils = require(resolve(dirname(require.resolve('@tailwindcss/typography')), 'utils.js'))

test('patched selector parser preserves typography shared pseudo handling', () => {
  assert.deepEqual(typographyUtils.commonTrailingPseudos('a::before,b::before'), ['::before', 'a,b'])
  assert.deepEqual(typographyUtils.commonTrailingPseudos('a::before,b::after'), [null, 'a::before,b::after'])
})

test('Markdown math renders through the retained sanitizer and KaTeX plugins', () => {
  const html = renderToStaticMarkup(React.createElement(ReactMarkdown, {
    remarkPlugins: [remarkMath], rehypePlugins: [rehypeSanitize, rehypeKatex],
    children: 'Energy: $E=mc^2$.',
  }))
  assert.match(html, /class="katex/)
  assert.match(html, /<math /)
  assert.match(html, /Energy:/)
})

test('KaTeX rejects inherited trust while preserving explicitly trusted rendering', () => {
  const expression = String.raw`\href{https://example.com}{reference}`
  const inherited = Object.create({ trust: true })
  inherited.throwOnError = false
  assert.doesNotMatch(katex.renderToString(expression, inherited), /<a\b/)
  assert.match(katex.renderToString(expression, { trust: true }), /<a\b/)
})
