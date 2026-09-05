import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'
import { runInNewContext } from 'node:vm'

const require = createRequire(import.meta.url)
const { transpileModule, ModuleKind, JsxEmit, ScriptTarget } = require('typescript')
const { clsx } = require('clsx')
const { twMerge } = require('tailwind-merge')
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')

function componentExports(relativePath) {
  const filename = new URL(relativePath, import.meta.url)
  const compiled = transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ModuleKind.CommonJS, jsx: JsxEmit.ReactJSX, target: ScriptTarget.ES2020 },
  }).outputText
  const exports = {}
  runInNewContext(compiled, {
    exports,
    require: (specifier) => specifier === '@/lib/utils' ? { cn: (...values) => twMerge(clsx(values)) } : require(specifier),
  }, { filename: filename.pathname })
  return exports
}

const { Button, buttonVariants } = componentExports('../src/components/ui/button.tsx')
const { badgeVariants } = componentExports('../src/components/ui/badge.tsx')

const stylesheet = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8')
const bootstrap = html.match(/<script>([\s\S]*?)<\/script>/)[1]

function cssTokens(selector) {
  const block = stylesheet.match(new RegExp(`  ${selector} \\{([\\s\\S]*?)\\n  \\}`))[1]
  return Object.fromEntries([...block.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((match) => [match[1], match[2]]))
}

const themes = { light: cssTokens(':root'), dark: cssTokens('\\.dark') }

function hslToRgb(value) {
  assert.equal(typeof value, 'string', 'Every used color needs an explicit token')
  const [hue, saturation, lightness] = value.match(/[\d.]+/g).map(Number)
  const sat = saturation / 100
  const light = lightness / 100
  const chroma = (1 - Math.abs(2 * light - 1)) * sat
  const secondary = chroma * (1 - Math.abs((hue / 60) % 2 - 1))
  const offset = light - chroma / 2
  const channels = hue < 60 ? [chroma, secondary, 0]
    : hue < 120 ? [secondary, chroma, 0]
      : hue < 180 ? [0, chroma, secondary]
        : hue < 240 ? [0, secondary, chroma]
          : hue < 300 ? [secondary, 0, chroma]
            : [chroma, 0, secondary]
  return channels.map((channel) => channel + offset)
}

function luminance(value) {
  return hslToRgb(value)
    .map((channel) => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4)
    .reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0)
}

function assertReadable(background, foreground, description) {
  const first = luminance(background)
  const second = luminance(foreground)
  const contrast = (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05)
  assert.ok(contrast >= 4.5, `${description}: ${contrast.toFixed(3)}:1 is below 4.5:1`)
}

function checkFilledVariant(classes, tokens, description, interactive) {
  const background = classes.match(/(?:^|\s)bg-([\w-]+)(\/\d+)?(?:\s|$)/)
  const foreground = classes.match(/(?:^|\s)text-([\w-]+-foreground)(?:\s|$)/)
  const hover = classes.match(/(?:^|\s)hover:bg-([\w-]+)(\/\d+)?(?:\s|$)/)
  assert.ok(background && foreground, `${description} declares its foreground and background together`)
  assert.equal(background[2], undefined, `${description} uses an opaque background`)
  assertReadable(tokens[`--${background[1]}`], tokens[`--${foreground[1]}`], description)
  if (interactive) {
    assert.ok(hover, `${description} has a visible hover state`)
    assert.equal(hover[2], undefined, `${description} uses an opaque hover background`)
    assertReadable(tokens[`--${hover[1]}`], tokens[`--${foreground[1]}`], `${description} hover`)
  } else {
    assert.equal(hover, null, `${description} does not imply an action on hover`)
  }
}

function documentRoot() {
  const styles = new Map()
  const classes = new Set()
  return {
    styles,
    classes,
    style: {
      setProperty: (name, value) => styles.set(name, value),
      removeProperty: (name) => styles.delete(name),
    },
    classList: {
      add: (value) => classes.add(value),
      toggle: (value, enabled) => enabled ? classes.add(value) : classes.delete(value),
    },
  }
}

const storage = new Map()
globalThis.localStorage = {
  getItem: (key) => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: (key) => storage.delete(key),
}
globalThis.document = { documentElement: documentRoot() }
globalThis.window = {
  localStorage: globalThis.localStorage,
  matchMedia: () => ({ matches: false, addEventListener: () => {} }),
}
const { ACCENTS, useUIStore } = await import('../src/stores/ui-store.ts')

for (const [theme, tokens] of Object.entries(themes)) {
  test(`${theme} filled status controls retain readable text`, () => {
    for (const semantic of ['success', 'warning', 'info', 'destructive', 'secondary']) {
      assertReadable(tokens[`--${semantic}`], tokens[`--${semantic}-foreground`], `${theme} ${semantic}`)
    }
  })

  test(`${theme} filled control hover colors retain readable text`, () => {
    for (const semantic of ['destructive', 'secondary']) {
      assertReadable(tokens[`--${semantic}-hover`], tokens[`--${semantic}-foreground`], `${theme} ${semantic} hover`)
    }
  })

  for (const accent of Object.keys(ACCENTS)) {
    test(`${theme} ${accent} appearance is readable before and after hydration`, () => {
      const beforeHydration = documentRoot()
      runInNewContext(bootstrap, {
        localStorage: { getItem: () => JSON.stringify({ state: { theme, accent } }) },
        document: { documentElement: beforeHydration },
        window: globalThis.window,
      })

      const afterHydration = documentRoot()
      globalThis.document.documentElement = afterHydration
      useUIStore.getState().setTheme(theme)
      useUIStore.getState().setAccent(accent)

      assert.deepEqual(afterHydration.styles, beforeHydration.styles, 'Theme bootstrap and settings must agree')
      assert.deepEqual(afterHydration.classes, beforeHydration.classes)
      const applied = { ...tokens, ...Object.fromEntries(afterHydration.styles) }
      assertReadable(applied['--primary'], applied['--primary-foreground'], `${theme} ${accent}`)
      assertReadable(applied['--primary-hover'], applied['--primary-foreground'], `${theme} ${accent} hover`)
      for (const variant of ['default', 'destructive', 'secondary']) {
        checkFilledVariant(buttonVariants({ variant }), applied, `${theme} ${accent} ${variant} button`, true)
      }
      for (const variant of ['default', 'success', 'warning', 'info', 'destructive', 'secondary']) {
        checkFilledVariant(badgeVariants({ variant }), applied, `${theme} ${accent} ${variant} badge`, false)
      }
    })
  }
}

test('returning to the default accent clears every custom color override', () => {
  const root = documentRoot()
  globalThis.document.documentElement = root
  useUIStore.getState().setTheme('light')
  useUIStore.getState().setAccent('amber')
  assert.ok(root.styles.size > 0)
  useUIStore.getState().setAccent('teal')
  assert.equal(root.styles.size, 0)
})

test('invalid persisted accent names recover to theme defaults', () => {
  for (const accent of ['unknown', 'constructor', '__proto__', 'toString']) {
    const beforeHydration = documentRoot()
    runInNewContext(bootstrap, {
      localStorage: { getItem: () => JSON.stringify({ state: { theme: 'dark', accent } }) },
      document: { documentElement: beforeHydration },
      window: globalThis.window,
    })
    assert.equal(beforeHydration.styles.size, 0, `${accent} cannot create invalid bootstrap colors`)

    const afterHydration = documentRoot()
    globalThis.document.documentElement = afterHydration
    useUIStore.getState().setTheme('dark')
    useUIStore.getState().setAccent('amber')
    useUIStore.getState().setAccent(accent)
    assert.equal(afterHydration.styles.size, 0, `${accent} clears previous accent overrides`)
  }
})

test('Button asChild renders its link without adding a nested button', () => {
  const html = renderToStaticMarkup(React.createElement(Button, { asChild: true },
    React.createElement('a', { href: '/experts' }, 'Browse experts')))
  assert.match(html, /^<a /)
  assert.match(html, /href="\/experts"/)
  assert.match(html, />Browse experts<\/a>$/)
  assert.doesNotMatch(html, /<button|\saria-disabled=|\saria-busy=/)
})

test('loading slotted links retain one target, a spinner, and unavailable state', () => {
  const html = renderToStaticMarkup(React.createElement(Button, { asChild: true, loading: true },
    React.createElement('a', { href: '/experts' }, 'Browse experts')))
  assert.match(html, /^<a /)
  assert.match(html, /aria-disabled="true"/)
  assert.match(html, /aria-busy="true"/)
  assert.match(html, /tabindex="-1"/)
  assert.match(html, /<svg[^>]*aria-hidden="true"/)
  assert.match(html, /Browse experts<\/a>$/)
})

test('unavailable slotted controls stop activation before child click handlers', () => {
  for (const unavailable of [{ disabled: true }, { loading: true }]) {
    const observed = []
    const element = Button.render({
      asChild: true,
      ...unavailable,
      onClickCapture: () => observed.push('caller'),
      children: React.createElement('a', { href: '/experts' }, 'Browse experts'),
    }, null)
    element.props.onClickCapture({
      preventDefault: () => observed.push('prevented'),
      stopPropagation: () => observed.push('stopped'),
    })
    assert.deepEqual(observed, ['prevented', 'stopped'])
    assert.equal(element.props.tabIndex, -1)
  }
})

test('available slotted controls preserve caller capture and tab order', () => {
  const observed = []
  const event = {}
  const element = Button.render({
    asChild: true,
    tabIndex: 0,
    onClickCapture: (value) => observed.push(value),
    children: React.createElement('a', { href: '/experts' }, 'Browse experts'),
  }, null)
  element.props.onClickCapture(event)
  assert.deepEqual(observed, [event])
  assert.equal(element.props.tabIndex, 0)
})

test('ordinary loading buttons retain native disabled semantics', () => {
  const html = renderToStaticMarkup(React.createElement(Button, { loading: true }, 'Create expert'))
  assert.match(html, /^<button /)
  assert.match(html, /disabled=""/)
  assert.match(html, /aria-busy="true"/)
  assert.match(html, /<svg[^>]*aria-hidden="true"/)
  assert.match(html, /Create expert<\/button>$/)
})
