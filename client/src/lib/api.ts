// api.ts — the browser's calls to the Python Cash backend (mounted at /api on
// the gateway). In dev, Vite proxies /api to the gateway (see vite.config.ts);
// in production the client is served same-origin behind nginx which proxies
// /api. Every call sends the session cookie (credentials: 'include').

export interface ApiResult<T> {
  ok: boolean
  status: number
  data: T
  error?: string
}

export async function api<T = unknown>(
  method: string,
  path: string,
  body?: unknown,
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`/api${path}`, {
      method,
      credentials: 'include',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
    let data: unknown = null
    try {
      data = await res.json()
    } catch {
      data = null
    }
    const error = !res.ok ? ((data as { error?: string })?.error || res.statusText) : undefined
    return { ok: res.ok, status: res.status, data: data as T, error }
  } catch (e) {
    return { ok: false, status: 0, data: null as T, error: (e as Error).message }
  }
}

// --- connectors ---
export interface Connector {
  id: string
  title: string
  available: boolean
  connected: boolean
  unlocks: string[]
  connect_hint: string
}

export async function fetchConnectors(): Promise<Connector[]> {
  const res = await api<{ connectors: Connector[] }>('GET', '/connectors')
  return res.ok ? res.data.connectors : []
}

export async function disconnectConnector(id: string): Promise<boolean> {
  const res = await api<{ disconnected: boolean }>('POST', `/connectors/${id}/disconnect`)
  return res.ok && res.data.disconnected
}

// --- chat ---
export interface ChatResponse {
  reply: string
  action?: string
}

export async function sendChat(message: string): Promise<ChatResponse> {
  const res = await api<ChatResponse>('POST', '/chat', { message })
  if (res.ok && typeof res.data.reply === 'string') return res.data
  return { reply: "😿 I couldn't reach the backend just now — try again in a moment." }
}

// --- conversations (persistent chat threads, addressed by id) ---
export interface Conversation { id: string; title: string; created_at: string; updated_at: string }
export interface Message { id: string; role: 'user' | 'assistant'; content: string; action?: string; createdAt: string }

export async function listConversations(): Promise<Conversation[]> {
  const res = await api<{ conversations: Conversation[] }>('GET', '/conversations')
  return res.ok ? res.data.conversations : []
}

export async function createConversation(): Promise<Conversation | null> {
  const res = await api<{ conversation: Conversation }>('POST', '/conversations')
  return res.ok ? res.data.conversation : null
}

export async function getConversation(id: string): Promise<{ conversation: Conversation; messages: Message[] } | null> {
  const res = await api<{ conversation: Conversation; messages: Message[] }>('GET', `/conversations/${id}/messages`)
  return res.ok ? res.data : null
}

export async function sendConversationMessage(id: string, message: string): Promise<ChatResponse> {
  const res = await api<ChatResponse>('POST', `/conversations/${id}/messages`, { message })
  if (res.ok && typeof res.data.reply === 'string') return res.data
  return { reply: "😿 I couldn't reach the backend just now — try again in a moment." }
}

export async function deleteConversation(id: string): Promise<boolean> {
  const res = await api<{ deleted: boolean }>('DELETE', `/conversations/${id}`)
  return res.ok && res.data.deleted
}
