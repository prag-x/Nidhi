const TOKEN_KEY = 'nidhi.token'

export class ApiError extends Error {
  status: number
  /** Structured detail when the server sends one (e.g. coordination conflicts). */
  data: Record<string, unknown> | null
  constructor(status: number, message: string, data: Record<string, unknown> | null = null) {
    super(message)
    this.status = status
    this.data = data
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable (private mode); session continues in memory */
  }
}

let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

type Params = Record<string, string | number | boolean | null | undefined>

export function qs(params?: Params): string {
  if (!params) return ''
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '' || v === false) continue
    sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return new ApiError(res.status, body.detail)
    if (Array.isArray(body.detail)) {
      return new ApiError(
        res.status,
        body.detail.map((d: { loc?: string[]; msg: string }) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg}`).join('; '),
      )
    }
    if (body.detail && typeof body.detail === 'object') {
      return new ApiError(res.status, String(body.detail.message ?? `Request failed (${res.status})`), body.detail)
    }
  } catch {
    /* not JSON */
  }
  return new ApiError(res.status, `Request failed (${res.status})`)
}

export async function request<T>(method: string, path: string, body?: unknown, params?: Params): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(`/api${path}${qs(params)}`, { method, headers, body: payload })
  if (res.status === 401 && token) onUnauthorized?.()
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string, params?: Params) => request<T>('GET', path, undefined, params),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body ?? {}),
}

/** Fetch a file with the session token and hand it to the browser as a download. */
export async function download(path: string, params?: Params, fallbackName = 'download') {
  const token = getToken()
  const res = await fetch(`/api${path}${qs(params)}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw await parseError(res)
  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition') ?? ''
  const match = /filename="?([^"]+)"?/.exec(disposition)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = match?.[1] ?? fallbackName
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  return 'Something went wrong'
}
