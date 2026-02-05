import { useState, useEffect } from 'react'

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false)

  useEffect(() => {
    const mql = window.matchMedia(query)
    setMatches(mql.matches)
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [query])

  return matches
}

export function useIsMobile() { return useMediaQuery('(max-width: 767px)') }
export function useIsTablet() { return useMediaQuery('(min-width: 768px) and (max-width: 1023px)') }
export function useIsDesktop() { return useMediaQuery('(min-width: 1024px)') }
