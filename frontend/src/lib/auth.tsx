import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, getToken, setToken, setUnauthorizedHandler } from './api'
import type { User } from './types'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<User>
  logout: () => void
  /** AICTE staff (anyone who is not an institution). */
  isStaff: boolean
  /** Oversight: administrator, competent authority, RB head, auditor. */
  isGlobal: boolean
  isInstitution: boolean
  /** Lodges or scrutinises instruments (RB officers and head, institutions). */
  canLodge: boolean
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(Boolean(getToken()))
  const queryClient = useQueryClient()

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    queryClient.clear()
  }, [queryClient])

  useEffect(() => {
    setUnauthorizedHandler(logout)
    if (!getToken()) return
    api
      .get<User>('/auth/me')
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [logout])

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<{ access_token: string; user: User }>('/auth/login', { email, password })
    setToken(res.access_token)
    setUser(res.user)
    return res.user
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      login,
      logout,
      isStaff: !!user && user.role !== 'INSTITUTION',
      isGlobal: !!user && ['ADMIN', 'COMPETENT_AUTHORITY', 'RB_HEAD', 'AUDITOR'].includes(user.role),
      isInstitution: user?.role === 'INSTITUTION',
      canLodge: !!user && ['RB_OFFICER', 'RB_HEAD', 'INSTITUTION'].includes(user.role),
    }),
    [user, loading, login, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
