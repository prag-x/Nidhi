/**
 * Hindi / English. The language is chosen once per browser and the page reloads in it, so label tables built at
 * load time (statuses, timelines, actions) are always consistent. English text is the key; untranslated strings
 * fall back to English.
 */
import { HI } from './hi'

export type Lang = 'en' | 'hi'
const KEY = 'nidhi.lang'

function read(): Lang {
  try {
    return localStorage.getItem(KEY) === 'hi' ? 'hi' : 'en'
  } catch {
    return 'en'
  }
}

export const lang: Lang = read()
if (typeof document !== 'undefined') document.documentElement.lang = lang === 'hi' ? 'hi' : 'en'

export function setLang(next: Lang) {
  try {
    localStorage.setItem(KEY, next)
  } catch {
    /* storage unavailable: the choice lasts until reload */
  }
  window.location.reload()
}

/** Translate `s`; `{name}` placeholders are filled from `vars`. */
export function t(s: string, vars?: Record<string, string | number>): string {
  let out = lang === 'hi' ? (HI[s] ?? s) : s
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.replaceAll(`{${k}}`, String(v))
  return out
}

export const isHindi = lang === 'hi'
