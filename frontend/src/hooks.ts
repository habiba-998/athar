import { useEffect, useState } from 'react'

/** Tracks a CSS media query. Safe when matchMedia is unavailable. */
export function useMediaQuery(query: string): boolean {
  const get = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(query).matches
  const [match, setMatch] = useState(get)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia(query)
    const on = () => setMatch(mq.matches)
    mq.addEventListener('change', on)
    on()
    return () => mq.removeEventListener('change', on)
  }, [query])
  return match
}

/** True on phones (<= 640px): graph and route traces switch to vertical layouts. */
export const useNarrow = () => useMediaQuery('(max-width: 640px)')
