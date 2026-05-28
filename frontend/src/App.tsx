import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { hasToken } from './api/client'
import AuthCallbackPage from './pages/AuthCallbackPage'
import ChatPage from './pages/ChatPage'
import LoginPage from './pages/LoginPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  return hasToken() ? <>{children}</> : <Navigate to="/" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route
          path="/chat"
          element={
            <RequireAuth>
              <ChatPage />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
