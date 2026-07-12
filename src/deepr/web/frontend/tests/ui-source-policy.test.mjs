import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import test from 'node:test'

const sourceRoot = new URL('../src/', import.meta.url)
const sourceExtensions = new Set(['.css', '.html', '.ts', '.tsx'])

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const child = new URL(entry.name, directory)
    if (entry.isDirectory()) {
      child.pathname += '/'
      files.push(...(await sourceFiles(child)))
    } else if ([...sourceExtensions].some((extension) => entry.name.endsWith(extension))) {
      files.push(child)
    }
  }
  return files
}

test('authored frontend source uses icons and plain hyphens', async () => {
  for (const file of await sourceFiles(sourceRoot)) {
    const source = await readFile(file, 'utf8')
    assert.doesNotMatch(source, /\p{Extended_Pictographic}/u, `${file.pathname} contains an emoji glyph`)
    assert.doesNotMatch(source, /[\u2013\u2014]/u, `${file.pathname} contains an en or em dash`)
  }
})
