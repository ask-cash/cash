import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import ProtectedRoute from './components/ProtectedRoute'
import SignUp from './pages/SignUp'
import SignIn from './pages/SignIn'
import Onboarding from './pages/Onboarding'
import ConnectCalendar from './pages/ConnectCalendar'
import DashboardLayout from './pages/dashboard/Layout'
import Chat from './pages/dashboard/Chat'
import Integrations from './pages/dashboard/Integrations'
import Settings from './pages/dashboard/Settings'

// Send the visitor to the right place: signed-in → dashboard, else → sign in.
function Landing() {
  const { user, loading } = useAuth()
  if (loading) return null
  return <Navigate to={user ? '/app' : '/signin'} replace />
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/signup" element={<SignUp />} />
          <Route path="/signin" element={<SignIn />} />

          {/* Signed in, but onboarding may be incomplete. */}
          <Route
            path="/onboarding"
            element={<ProtectedRoute requireOnboarded={false}><Onboarding /></ProtectedRoute>}
          />
          <Route
            path="/connect-calendar"
            element={<ProtectedRoute requireOnboarded={false}><ConnectCalendar /></ProtectedRoute>}
          />

          {/* The dashboard proper. */}
          <Route path="/app" element={<ProtectedRoute><DashboardLayout /></ProtectedRoute>}>
            <Route index element={<Chat />} />
            <Route path="integrations" element={<Integrations />} />
            <Route path="settings" element={<Settings />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
