import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import useAuthStore from './store/authStore'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import DashboardPage from './pages/DashboardPage'
import CustomersPage from './pages/CustomersPage'
import CustomerDetailPage from './pages/CustomerDetailPage'
import EstimateBuilderPage from './pages/EstimateBuilderPage'
import EditorPage from './pages/EditorPage'
import RatesPage from './pages/RatesPage'

function ProtectedRoute({ children }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  return isAuthenticated ? children : <Navigate to="/login" replace />
}

function AdminRoute({ children }) {
  const user = useAuthStore((s) => s.user)
  if (!user) return <Navigate to="/login" replace />
  if (!user.is_admin) return <Navigate to="/" replace />
  return children
}

export default function App() {
  const fetchMe = useAuthStore((s) => s.fetchMe)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  useEffect(() => {
    if (isAuthenticated) fetchMe()
  }, [])

  return (
    <BrowserRouter>
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: 'var(--c-surface-2)',
            color: 'var(--c-text)',
            border: '1px solid var(--c-border)',
            fontFamily: 'var(--font-sans)',
          },
          success: { iconTheme: { primary: 'var(--c-success)', secondary: 'var(--c-surface)' } },
          error: { iconTheme: { primary: 'var(--c-error)', secondary: 'var(--c-surface)' } },
        }}
      />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/" element={<ProtectedRoute><CustomersPage /></ProtectedRoute>} />
        <Route path="/customers/:id" element={<ProtectedRoute><CustomerDetailPage /></ProtectedRoute>} />
        <Route path="/estimates/:id" element={<ProtectedRoute><EstimateBuilderPage /></ProtectedRoute>} />
        <Route path="/estimates/:estimateId/frames/:frameId" element={<ProtectedRoute><EditorPage /></ProtectedRoute>} />
        <Route path="/designs" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
        <Route path="/designs/:id" element={<ProtectedRoute><EditorPage /></ProtectedRoute>} />
        <Route path="/rates" element={<AdminRoute><RatesPage /></AdminRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
