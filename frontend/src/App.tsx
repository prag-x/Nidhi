import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import { Loading } from './components/ui'
import { useAuth } from './lib/auth'
import Login from './pages/Login'

const Home = lazy(() => import('./pages/Home'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Instruments = lazy(() => import('./pages/Instruments'))
const InstrumentDetail = lazy(() => import('./pages/InstrumentDetail'))
const NewInstrument = lazy(() => import('./pages/NewInstrument'))
const Maturity = lazy(() => import('./pages/Maturity'))
const Releases = lazy(() => import('./pages/Releases'))
const Institutions = lazy(() => import('./pages/Institutions'))
const InstitutionProfile = lazy(() => import('./pages/InstitutionProfile'))
const Alerts = lazy(() => import('./pages/Alerts'))
const Reports = lazy(() => import('./pages/Reports'))
const Integrity = lazy(() => import('./pages/Integrity'))
const Proof = lazy(() => import('./pages/Proof'))
const Ask = lazy(() => import('./pages/Ask'))
const Admin = lazy(() => import('./pages/Admin'))
const Verify = lazy(() => import('./pages/Verify'))
const NotFound = lazy(() => import('./pages/NotFound'))

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <Loading label="Signing you in…" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <>{children}</>
}

export default function App() {
  const { user } = useAuth()
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        {!user && <Route path="/verify/:code?" element={<Verify />} />}
        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route index element={<Home />} />
          <Route path="overview" element={<Dashboard />} />
          <Route path="instruments" element={<Instruments />} />
          <Route path="instruments/new" element={<NewInstrument />} />
          <Route path="instruments/:id" element={<InstrumentDetail />} />
          <Route path="maturity" element={<Maturity />} />
          <Route path="releases" element={<Releases />} />
          <Route path="institutions" element={<Institutions />} />
          <Route path="institutions/:id" element={<InstitutionProfile />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="reports" element={<Reports />} />
          <Route path="integrity" element={<Integrity />} />
          <Route path="proof" element={<Proof />} />
          <Route path="ask" element={<Ask />} />
          <Route path="admin" element={<Admin />} />
          <Route path="verify/:code?" element={<Verify />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
