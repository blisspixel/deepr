import { useState, useCallback, useRef } from 'react'

export function useLocalStorage<T>(key: string, initialValue: T): [T, (value: T | ((prev: T) => T)) => void] {
  const [storedValue, setStoredValue] = useState<T>(() => {
    try {
      const item = window.localStorage.getItem(key)
      return item ? JSON.parse(item) : initialValue
    } catch { return initialValue }
  })

  // Use ref to avoid stale closure when setValue is called with a function updater
  const storedValueRef = useRef(storedValue)
  storedValueRef.current = storedValue

  const setValue = useCallback((value: T | ((prev: T) => T)) => {
    const valueToStore = value instanceof Function ? value(storedValueRef.current) : value
    storedValueRef.current = valueToStore
    setStoredValue(valueToStore)
    window.localStorage.setItem(key, JSON.stringify(valueToStore))
  }, [key])

  return [storedValue, setValue]
}
