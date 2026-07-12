import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import CashMark from '../../components/CashMark'
import { SendIcon, PlusIcon } from '../../components/icons'
import { useAuth } from '../../lib/auth'
import {
  listConversations, createConversation, getConversation,
  sendConversationMessage, deleteConversation,
  type Conversation, type Message,
} from '../../lib/api'

const STARTERS = [
  "What's on my calendar today?",
  'Remind me to call mom at 6pm',
  'Give me a morning brief',
  'What did I say I wanted to do this week?',
]

export default function Chat() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [convos, setConvos] = useState<Conversation[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)

  const refreshConvos = useCallback(async () => setConvos(await listConversations()), [])

  // Ensure a conversation exists and load its transcript for the id in the URL.
  useEffect(() => {
    let cancelled = false
    async function boot() {
      const list = await listConversations()
      if (cancelled) return
      setConvos(list)
      if (!conversationId) {
        if (list.length) { navigate(`/app/chat/${list[0].id}`, { replace: true }); return }
        const c = await createConversation()
        if (c && !cancelled) navigate(`/app/chat/${c.id}`, { replace: true })
        return
      }
      const data = await getConversation(conversationId)
      if (!cancelled) setMessages(data ? data.messages : [])
    }
    boot()
    return () => { cancelled = true }
  }, [conversationId, navigate])

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, thinking])

  function autosize() {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 180) + 'px'
  }

  async function send() {
    const text = input.trim()
    if (!text || thinking || !conversationId) return
    setInput('')
    requestAnimationFrame(autosize)
    setMessages((m) => [...m, { id: 'tmp-' + Date.now(), role: 'user', content: text, createdAt: '' }])
    setThinking(true)
    const { reply } = await sendConversationMessage(conversationId, text)
    setThinking(false)
    setMessages((m) => [...m, { id: 'a-' + Date.now(), role: 'assistant', content: reply, createdAt: '' }])
    refreshConvos()
  }

  async function newChat() {
    const c = await createConversation()
    if (c) { setMessages([]); navigate(`/app/chat/${c.id}`); refreshConvos() }
  }

  async function removeConvo(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    await deleteConversation(id)
    const list = await listConversations()
    setConvos(list)
    if (id === conversationId) navigate(list.length ? `/app/chat/${list[0].id}` : '/app/chat', { replace: true })
  }

  const empty = messages.length === 0 && !thinking

  return (
    <div className="chat-shell">
      <aside className="conv-rail">
        <button className="conv-new" onClick={newChat}><PlusIcon /> New chat</button>
        <div className="conv-list-label">Recents</div>
        <div className="conv-scroll">
          {convos.length === 0 && <div className="conv-empty-rail">No conversations yet.</div>}
          {convos.map((c) => (
            <div
              key={c.id}
              className={'conv-item' + (c.id === conversationId ? ' active' : '')}
              onClick={() => navigate(`/app/chat/${c.id}`)}
            >
              <span className="ci-title">{c.title}</span>
              <button className="ci-del" onClick={(e) => removeConvo(e, c.id)} aria-label="Delete conversation">×</button>
            </div>
          ))}
        </div>
      </aside>

      <div className="chat">
        <div className="chat-log" ref={logRef}>
          {empty ? (
            <div className="chat-greeting">
              <span className="mark"><CashMark /></span>
              <h2>Hey {user?.profile.firstName || 'there'} 👋</h2>
              <p>I'm Cash. Ask me about your day, your calendar, a reminder — same brain and memory as Telegram.</p>
              <div className="starters">
                {STARTERS.map((s) => (
                  <button key={s} className="starter" onClick={() => { setInput(s); taRef.current?.focus() }}>{s}</button>
                ))}
              </div>
            </div>
          ) : (
            <div className="chat-thread">
              {messages.map((m) => (
                <div key={m.id} className={'turn ' + m.role}>
                  <span className="avatar">
                    {m.role === 'assistant' ? <CashMark /> : (user?.profile.firstName?.[0]?.toUpperCase() || 'Y')}
                  </span>
                  <div className="content">{m.content}</div>
                </div>
              ))}
              {thinking && (
                <div className="turn assistant">
                  <span className="avatar"><CashMark /></span>
                  <div className="content typing"><span></span><span></span><span></span></div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="composer-wrap">
          <div className="composer">
            <textarea
              ref={taRef}
              value={input}
              rows={1}
              placeholder="Message Cash…"
              onChange={(e) => { setInput(e.target.value); autosize() }}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            />
            <button className="send-btn" onClick={send} disabled={!input.trim() || thinking} aria-label="Send">
              <SendIcon />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
