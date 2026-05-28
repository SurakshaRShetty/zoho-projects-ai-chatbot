import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { hasToken, LOGIN_URL } from '../api/client'

export default function LoginPage() {
  const navigate = useNavigate()

  useEffect(() => {
    if (hasToken()) navigate('/chat', { replace: true })
  }, [navigate])

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-100 to-blue-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl p-10 w-full max-w-md text-center">
        {/* Logo / Icon */}
        <div className="flex justify-center mb-6">
          <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center shadow-md">
            <svg className="w-9 h-9 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
        </div>

        <h1 className="text-2xl font-bold text-slate-800 mb-2">Zoho Projects Assistant</h1>
        <p className="text-slate-500 mb-8 text-sm leading-relaxed">
          Connect your Zoho Projects account to manage tasks, track progress, and get AI-powered insights — all through natural conversation.
        </p>

        <a
          href={LOGIN_URL}
          className="flex items-center justify-center gap-3 w-full bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-semibold py-3 px-6 rounded-xl transition-colors duration-150 shadow-sm"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm4.5 7.5h-3v7h-3v-7h-3V7h9v2.5z" />
          </svg>
          Login with Zoho Projects
        </a>

        <p className="mt-6 text-xs text-slate-400">
          You'll be redirected to Zoho to authorise access. No passwords are stored.
        </p>
      </div>
    </div>
  )
}
