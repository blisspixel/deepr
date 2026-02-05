import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'light' | 'dark' | 'system'

interface UIState {
  sidebarCollapsed: boolean
  theme: Theme
  setSidebarCollapsed: (collapsed: boolean) => void
  toggleSidebar: () => void
  setTheme: (theme: Theme) => void
  cycleTheme: () => void
}

function applyThemeToDocument(theme: Theme) {
  const root = document.documentElement

  if (theme === 'system') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    root.classList.toggle('dark', prefersDark)
    root.classList.toggle('light', !prefersDark)
  } else {
    root.classList.toggle('dark', theme === 'dark')
    root.classList.toggle('light', theme === 'light')
  }
}

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
      sidebarCollapsed: false,
      theme: 'system',

      setSidebarCollapsed: (collapsed: boolean) => set({ sidebarCollapsed: collapsed }),

      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

      setTheme: (theme: Theme) => {
        applyThemeToDocument(theme)
        set({ theme })
      },

      cycleTheme: () => {
        const themes: Theme[] = ['light', 'dark', 'system']
        const currentIndex = themes.indexOf(get().theme)
        const nextTheme = themes[(currentIndex + 1) % themes.length]
        applyThemeToDocument(nextTheme)
        set({ theme: nextTheme })
      },
    }),
    {
      name: 'deepr-ui-store',
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        theme: state.theme,
      }),
      onRehydrateStorage: () => {
        return (state) => {
          if (state) {
            applyThemeToDocument(state.theme)
          }
        }
      },
    }
  )
)

// Listen for system theme changes when theme is 'system'
if (typeof window !== 'undefined') {
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  mediaQuery.addEventListener('change', () => {
    const { theme } = useUIStore.getState()
    if (theme === 'system') {
      applyThemeToDocument('system')
    }
  })
}
