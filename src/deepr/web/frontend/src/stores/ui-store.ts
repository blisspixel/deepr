import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'light' | 'dark' | 'system'
export type Accent =
  | 'teal'
  | 'indigo'
  | 'blue'
  | 'violet'
  | 'emerald'
  | 'amber'
  | 'rose'
  | 'cyan'

/**
 * Filled controls use opaque rest and hover colors with the theme's shared
 * foreground. 'teal' clears all overrides so the CSS defaults win. Keep these
 * values in sync with the synchronous appearance bootstrap in index.html.
 */
export const ACCENTS: Record<Accent, {
  label: string
  light: string
  dark: string
  lightHover: string
  darkHover: string
}> = {
  teal: { label: 'Teal', light: '172 65% 27%', dark: '172 50% 48%', lightHover: '172 65% 23%', darkHover: '172 50% 55%' },
  indigo: { label: 'Indigo', light: '243 55% 48%', dark: '243 72% 72%', lightHover: '243 55% 42%', darkHover: '243 72% 78%' },
  blue: { label: 'Blue', light: '217 80% 40%', dark: '213 85% 66%', lightHover: '217 80% 34%', darkHover: '213 85% 73%' },
  violet: { label: 'Violet', light: '262 60% 47%', dark: '263 78% 73%', lightHover: '262 60% 41%', darkHover: '263 78% 79%' },
  emerald: { label: 'Emerald', light: '158 70% 25%', dark: '156 60% 48%', lightHover: '158 70% 21%', darkHover: '156 60% 56%' },
  amber: { label: 'Amber', light: '32 90% 31%', dark: '38 92% 56%', lightHover: '32 90% 26%', darkHover: '38 92% 63%' },
  rose: { label: 'Rose', light: '346 72% 41%', dark: '346 82% 66%', lightHover: '346 72% 35%', darkHover: '346 82% 73%' },
  cyan: { label: 'Cyan', light: '191 82% 27%', dark: '189 78% 55%', lightHover: '191 82% 23%', darkHover: '189 78% 63%' },
}

const ACCENT_VARS = ['--primary', '--ring', '--sidebar-primary', '--sidebar-ring']
const ACCENT_HOVER_VAR = '--primary-hover'

interface UIState {
  sidebarCollapsed: boolean
  mobileMenuOpen: boolean
  theme: Theme
  accent: Accent
  setSidebarCollapsed: (collapsed: boolean) => void
  toggleSidebar: () => void
  setMobileMenuOpen: (open: boolean) => void
  setTheme: (theme: Theme) => void
  cycleTheme: () => void
  setAccent: (accent: Accent) => void
}

function resolveDark(theme: Theme): boolean {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  }
  return theme === 'dark'
}

/**
 * Apply both theme (light/dark class) and accent (CSS custom properties) in one
 * place. Accent shade depends on the resolved theme, so it must be re-applied
 * whenever the theme changes - not just when the accent changes.
 */
function applyAppearance(theme: Theme, accent: Accent) {
  const root = document.documentElement
  const dark = resolveDark(theme)
  root.classList.toggle('dark', dark)
  root.classList.toggle('light', !dark)

  if (accent === 'teal' || !Object.prototype.hasOwnProperty.call(ACCENTS, accent)) {
    ACCENT_VARS.forEach((v) => root.style.removeProperty(v))
    root.style.removeProperty(ACCENT_HOVER_VAR)
  } else {
    const value = dark ? ACCENTS[accent].dark : ACCENTS[accent].light
    ACCENT_VARS.forEach((v) => root.style.setProperty(v, value))
    root.style.setProperty(ACCENT_HOVER_VAR, dark ? ACCENTS[accent].darkHover : ACCENTS[accent].lightHover)
  }
}

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
      sidebarCollapsed: false,
      mobileMenuOpen: false,
      theme: 'system',
      accent: 'teal',

      setSidebarCollapsed: (collapsed: boolean) => set({ sidebarCollapsed: collapsed }),

      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

      setMobileMenuOpen: (open: boolean) => set({ mobileMenuOpen: open }),

      setTheme: (theme: Theme) => {
        applyAppearance(theme, get().accent)
        set({ theme })
      },

      cycleTheme: () => {
        const themes: Theme[] = ['light', 'dark', 'system']
        const currentIndex = themes.indexOf(get().theme)
        const nextTheme = themes[(currentIndex + 1) % themes.length]
        applyAppearance(nextTheme, get().accent)
        set({ theme: nextTheme })
      },

      setAccent: (accent: Accent) => {
        applyAppearance(get().theme, accent)
        set({ accent })
      },
    }),
    {
      name: 'deepr-ui-store',
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        theme: state.theme,
        accent: state.accent,
      }),
      onRehydrateStorage: () => {
        return (state) => {
          if (state) {
            applyAppearance(state.theme, state.accent)
          }
        }
      },
    }
  )
)

// Listen for system theme changes when theme is 'system'
// Single listener at module scope - safe since this module is only loaded once by the bundler
if (typeof window !== 'undefined') {
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  const handleSystemThemeChange = () => {
    const { theme, accent } = useUIStore.getState()
    if (theme === 'system') {
      applyAppearance('system', accent)
    }
  }
  mediaQuery.addEventListener('change', handleSystemThemeChange)
}
