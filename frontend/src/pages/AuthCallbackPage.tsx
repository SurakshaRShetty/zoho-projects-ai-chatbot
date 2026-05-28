import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { setToken } from '../api/client'

export default function AuthCallbackPage() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  // Prevent React 18 StrictMode double-invocation from running this twice.
  // The first run clears window.location.hash via replaceState, so the second
  // run would find no token and incorrectly set an error.
  const processed = useRef(false)

  useEffect(() => {
    if (processed.current) return
    processed.current = true

    // Token is passed as a URL fragment: /auth/callback#token=<jwt>
    const hash = window.location.hash.slice(1) // remove leading '#'
    const params = new URLSearchParams(hash)
    const token = params.get('token')
    const err = new URLSearchParams(window.location.search).get('error')

    if (err) {
      setError('Zoho authorisation failed. Please try again.')
      return
    }

    if (!token) {
      setError('No token received. Please try logging in again.')
      return
    }

    setToken(token)
    // Use navigate with replace:true — this removes /auth/callback#token=...
    // from history so the back button doesn't expose the token.
    navigate('/chat', { replace: true })
  }, [navigate])

  if (error) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-lg p-8 max-w-sm w-full text-center">
          <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-6 h-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-slate-800 mb-2">Authentication Failed</h2>
          <p className="text-slate-500 text-sm mb-6">{error}</p>
          <a href="/" className="inline-block bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-6 rounded-lg text-sm transition-colors">
            Back to Login
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <div className="text-center">
        <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-slate-500 text-sm">Completing sign-in…</p>
      </div>
    </div>
  )
}
