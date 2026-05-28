import type { ChatApiResponse, UserProfile } from '../types'

const API = 'http://localhost:8000'
const TOKEN_KEY = 'zoho_chatbot_token'

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export function hasToken(): boolean {
  return !!getToken()
}

export const LOGIN_URL = `${API}/auth/login`

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken()
  return fetch(`${API}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  })
}

export async function getMe(): Promise<UserProfile> {
  const res = await apiFetch('/auth/me')
  if (res.status === 401) throw new Error('UNAUTHORIZED')
  if (!res.ok) throw new Error(`SERVER_ERROR:${res.status}`)
  return res.json()
}

export async function sendChat(
  message: string,
  sessionId: string,
  confirmed?: boolean | null,
): Promise<ChatApiResponse> {
  const res = await apiFetch('/chat', {
    method: 'POST',
    body: JSON.stringify({
      message,
      session_id: sessionId,
      confirmed: confirmed ?? null,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? `Request failed: ${res.status}`)
  }
  return res.json()
}

export async function logout(): Promise<void> {
  await apiFetch('/auth/logout').catch(() => {})
  clearToken()
}
