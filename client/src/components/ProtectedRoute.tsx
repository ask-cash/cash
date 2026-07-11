import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'

// Gate a route behind auth. While the session hydrates we render nothing (a
// blank frame beats a flash of the login screen for an already-signed-in user).
// Once loaded, an unauthenticated visitor is bounced to /signin; a signed-in
// user who hasn't finished onboarding is sent back to complete it.
export default function ProtectedRoute({
  children,
  requireOnboarded = true,
}: {
  children: ReactNode
  requireOnboarded?: boolean
}) {
  const { user, loading } = useAuth()
  if (loading) return null
  if (!user) return <Navigate to="/signin" replace />
  if (requireOnboarded && !user.profile.onboarded) return <Navigate to="/onboarding" replace />
  return <>{children}</>
}
