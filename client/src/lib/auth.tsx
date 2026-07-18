import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from './api'

// The profile the backend returns for a signed-in user.
export interface Profile {
  firstName: string
  lastName: string
  email: string
  role?: string
  platforms?: string[]
  onboarded?: boolean
  calendarConnected?: boolean
  timezone?: string
}

export interface AuthUser {
  id: string
  email: string
  profile: Profile
}

interface AuthState {
  user: AuthUser | null
  loading: boolean
  signUp: (p: {
    firstName: string
    lastName: string
    email: string
    password: string
    timezone: string
  }) => Promise<string | null>
  signIn: (email: string, password: string) => Promise<string | null>
  signInWithGoogle: () => void
  signOut: () => Promise<void>
  updateProfile: (patch: Partial<Profile>) => Promise<string | null>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

// The backend returns a flat user object; fold it into our shape.
interface ApiUser {
  id: string
  email: string
  firstName: string
  lastName: string
  role?: string
  platforms?: string[]
  onboarded?: boolean
  calendarConnected?: boolean
  timezone?: string
}
function toUser(u: ApiUser | null): AuthUser | null {
  if (!u) return null
  return {
    id: u.id,
    email: u.email,
    profile: {
      firstName: u.firstName || '',
      lastName: u.lastName || '',
      email: u.email,
      role: u.role,
      platforms: u.platforms,
      onboarded: u.onboarded,
      calendarConnected: u.calendarConnected,
      timezone: u.timezone,
    },
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  async function loadMe() {
    const res = await api<{ user: ApiUser | null }>('GET', '/auth/me')
    setUser(res.ok ? toUser(res.data.user) : null)
  }

  useEffect(() => {
    loadMe().finally(() => setLoading(false))
  }, [])

  const value = useMemo<AuthState>(() => ({
    user,
    loading,

    async signUp(body) {
      const res = await api<{ user: ApiUser }>('POST', '/auth/signup', body)
      if (!res.ok) return res.error || 'Sign up failed.'
      setUser(toUser(res.data.user))
      return null
    },

    async signIn(email, password) {
      const res = await api<{ user: ApiUser }>('POST', '/auth/login', { email, password })
      if (!res.ok) return res.error || 'Sign in failed.'
      setUser(toUser(res.data.user))
      return null
    },

    signInWithGoogle() {
      // Full-page redirect into the backend's Google OAuth flow; it sets the
      // session cookie and redirects back to /app or /onboarding.
      window.location.href = '/api/auth/google/start'
    },

    async signOut() {
      await api('POST', '/auth/logout')
      setUser(null)
    },

    async updateProfile(patch) {
      const res = await api<{ user: ApiUser }>('PATCH', '/auth/profile', patch)
      if (!res.ok) return res.error || 'Your profile could not be updated.'
      setUser(toUser(res.data.user))
      return null
    },

    refresh: loadMe,
  }), [user, loading])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>')
  return ctx
}
