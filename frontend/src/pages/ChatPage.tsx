import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { clearToken, getMe, logout, sendChat } from '../api/client'
import ChatMessage from '../components/ChatMessage'
import TypingIndicator from '../components/TypingIndicator'
import type { Message, UserProfile } from '../types'

const WELCOME: Message = {
  id: 'welcome',
  role: 'assistant',
  content:
    "Hi! I'm your Zoho Projects assistant. I can help you:\n\n" +
    '• List and explore your projects\n' +
    '• View, create, update, or delete tasks\n' +
    '• Check team workload and task assignments\n\n' +
    'Try asking: "What are my projects?" or "Show open tasks in project Alpha"',
  timestamp: new Date(),
}

function newId() {
  return crypto.randomUUID()
}

function getOrCreateSessionId(): string {
  const key = 'zoho_chat_session_id'
  const stored = sessionStorage.getItem(key)
  if (stored) return stored
  const id = newId()
  sessionStorage.setItem(key, id)
  return id
}

export default function ChatPage() {
  const navigate = useNavigate()
  const [messages, setMessages] = useState<Message[]>([WELCOME])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [confirmLoading, setConfirmLoading] = useState(false)
  const [awaitingConfirmation, setAwaitingConfirmation] = useState(false)
  const [user, setUser] = useState<UserProfile | null>(null)
  const sessionId = useRef(getOrCreateSessionId())
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Load user profile — only clear token + redirect on a real 401.
  // Network errors (backend not yet ready) should NOT erase a valid token.
  useEffect(() => {
    getMe()
      .then(setUser)
      .catch((err: Error) => {
        if (err.message === 'UNAUTHORIZED') {
          clearToken()
          navigate('/', { replace: true })
        }
        // For network/server errors keep the token; the user can retry.
      })
  }, [navigate])

  // Scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  function addMessage(msg: Omit<Message, 'id' | 'timestamp'>) {
    setMessages((prev) => [
      ...prev,
      { ...msg, id: newId(), timestamp: new Date() },
    ])
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || loading || awaitingConfirmation) return
    setInput('')
    addMessage({ role: 'user', content: text })
    setLoading(true)
    try {
      const res = await sendChat(text, sessionId.current)
      if (res.type === 'confirmation_required') {
        addMessage({
          role: 'assistant',
          content: res.content,
          pendingAction: res.pending_action ?? undefined,
        })
        setAwaitingConfirmation(true)
      } else if (res.type === 'error') {
        addMessage({ role: 'error', content: res.content })
      } else {
        addMessage({ role: 'assistant', content: res.content })
      }
    } catch (err) {
      addMessage({
        role: 'error',
        content: err instanceof Error ? err.message : 'Failed to reach the server. Please try again.',
      })
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  async function handleConfirm(confirmed: boolean) {
    setAwaitingConfirmation(false)
    setConfirmLoading(true)
    try {
      const res = await sendChat('', sessionId.current, confirmed)
      if (res.type === 'error') {
        addMessage({ role: 'error', content: res.content })
      } else {
        addMessage({ role: 'assistant', content: res.content })
      }
    } catch (err) {
      addMessage({
        role: 'error',
        content: err instanceof Error ? err.message : 'Something went wrong.',
      })
    } finally {
      setConfirmLoading(false)
      inputRef.current?.focus()
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  async function handleLogout() {
    await logout()
    navigate('/', { replace: true })
  }

  const canSend = input.trim().length > 0 && !loading && !awaitingConfirmation

  // Find the index of the last message with a pending action (for confirmation UI)
  const lastConfirmIndex = awaitingConfirmation
    ? messages.map((m) => !!m.pendingAction).lastIndexOf(true)
    : -1

  return (
    <div className="flex flex-col h-screen bg-slate-50">
      {/* ── Header ─────────────────────────────────────────── */}
      <header className="bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between flex-shrink-0 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
          <div>
            <h1 className="text-sm font-semibold text-slate-800 leading-none">Zoho Projects Assistant</h1>
            {user && (
              <p className="text-xs text-slate-400 mt-0.5">{user.display_name || user.email}</p>
            )}
          </div>
        </div>

        <button
          onClick={handleLogout}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors px-2 py-1 rounded-lg hover:bg-slate-100"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          Logout
        </button>
      </header>

      {/* ── Messages ───────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto chat-scroll px-4 py-4">
        <div className="max-w-2xl mx-auto">
          {messages.map((msg, idx) => (
            <ChatMessage
              key={msg.id}
              message={msg}
              onConfirm={idx === lastConfirmIndex ? handleConfirm : undefined}
              confirmLoading={confirmLoading}
            />
          ))}
          {loading && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>
      </main>

      {/* ── Input area ─────────────────────────────────────── */}
      <div className="bg-white border-t border-slate-200 px-4 py-3 flex-shrink-0">
        <div className="max-w-2xl mx-auto">
          {awaitingConfirmation && (
            <p className="text-xs text-amber-600 mb-2 text-center font-medium">
              Please confirm or cancel the action above before sending a new message.
            </p>
          )}
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading || awaitingConfirmation}
              placeholder={awaitingConfirmation ? 'Waiting for confirmation…' : 'Ask about your projects or tasks…'}
              rows={1}
              className="flex-1 resize-none rounded-xl border border-slate-300 px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-slate-50 disabled:text-slate-400 transition-all"
              style={{ maxHeight: '120px' }}
              onInput={(e) => {
                const el = e.currentTarget
                el.style.height = 'auto'
                el.style.height = `${el.scrollHeight}px`
              }}
            />
            <button
              onClick={handleSend}
              disabled={!canSend}
              className="flex-shrink-0 w-10 h-10 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-200 text-white rounded-xl flex items-center justify-center transition-colors"
              title="Send (Enter)"
            >
              {loading ? (
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                </svg>
              )}
            </button>
          </div>
          <p className="text-xs text-slate-400 mt-1.5 text-center">
            Press <kbd className="bg-slate-100 px-1 py-0.5 rounded text-xs">Enter</kbd> to send · <kbd className="bg-slate-100 px-1 py-0.5 rounded text-xs">Shift+Enter</kbd> for new line
          </p>
        </div>
      </div>
    </div>
  )
}
