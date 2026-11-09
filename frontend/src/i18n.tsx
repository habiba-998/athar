import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { messages, type Lang, type MsgKey } from './messages'
import type { Asset } from './types'

export function translate(lang: Lang, key: string, params?: Record<string, string | number>): string {
  let s = (messages[lang] as Record<string, string>)[key] ?? key
  if (params) for (const [k, v] of Object.entries(params)) s = s.replaceAll(`{${k}}`, String(v))
  return s
}

interface Ctx {
  lang: Lang
  dir: 'ltr' | 'rtl'
  setLang: (l: Lang) => void
  t: (key: MsgKey | string, params?: Record<string, string | number>) => string
  assetName: (a: Asset | undefined) => string
  /** Numbers always use Latin digits (also in Arabic) so scores, ids and counts read identically in both languages. */
  num: (n: number) => string
  /** Direction-aware arrow for text such as routes: points the way the language reads. */
  arrow: string
}

const I18nContext = createContext<Ctx | null>(null)

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem('athar.lang')
    if (saved === 'ar' || saved === 'en') return saved
  } catch {
    // storage unavailable
  }
  return 'en'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang)
  const dir = lang === 'ar' ? 'rtl' : 'ltr'

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = dir
  }, [lang, dir])

  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    try {
      localStorage.setItem('athar.lang', l)
    } catch {
      // ignore
    }
  }, [])

  const value = useMemo<Ctx>(
    () => ({
      lang,
      dir,
      setLang,
      t: (key, params) => translate(lang, key, params),
      assetName: (a) => (a ? (lang === 'ar' ? a.name_ar : a.name) : ''),
      num: (n) => n.toLocaleString('en-US', { maximumFractionDigits: 1 }),
      arrow: dir === 'rtl' ? '←' : '→',
    }),
    [lang, dir, setLang],
  )
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): Ctx {
  const c = useContext(I18nContext)
  if (!c) throw new Error('I18nProvider missing')
  return c
}
