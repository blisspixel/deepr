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
 * Accent palette. Each entry carries a light and a dark HSL triple (matching the
 * `--primary` token format in index.css) so the chosen accent looks right in
 * both modes - a single value would be too dark in dark mode or too washed in
 * light mode. 'teal' is the default brand accent and clears the overrides so the
 * CSS defaults win. Keep this in sync with the inline FOUC map in index.html.
 */
export const ACCENTS: Record<Accent, { label: string; light: string; dark: string }> = {
  teal: { label: 'Teal', light: '172 66% 30%', dark: '172 52% 48%' },
  indigo: { label: 'Indigo', light: '243 55% 52%', dark: '243 72% 72%' },
  blue: { label: 'Blue', light: '217 80% 47%', dark: '213 85% 66%' },
  violet: { label: 'Violet', light: '262 60% 52%', dark: '263 78% 73%' },
  emerald: { label: 'Emerald', light: '158 70% 32%', dark: '156 60% 48%' },
  amber: { label: 'Amber', light: '32 90% 42%', dark: '38 92% 56%' },
  rose: { label: 'Rose', light: '346 72% 48%', dark: '346 82% 66%' },
  cyan: { label: 'Cyan', light: '191 82% 35%', dark: '189 78% 55%' },
}

const ACCENT_VARS = ['--primary', '--ring', '--sidebar-primary', '--sidebar-ring']

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

  if (accent === 'teal' || !ACCENTS[accent]) {
    ACCENT_VARS.forEach((v) => root.style.removeProperty(v))
  } else {
    const value = dark ? ACCENTS[accent].dark : ACCENTS[accent].light
    ACCENT_VARS.forEach((v) => root.style.setProperty(v, value))
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
