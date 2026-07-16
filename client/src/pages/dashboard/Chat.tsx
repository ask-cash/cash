import { useEffect, useRef, useState } from 'react'
import { useNavigate, useOutletContext, useParams } from 'react-router-dom'
import CashMark from '../../components/CashMark'
import {
  ChevronRightIcon,
  DownloadIcon,
  MonitorIcon,
  PaperclipIcon,
  RefreshIcon,
  SendIcon,
  ShieldIcon,
  SparklesIcon,
  MicIcon,
} from '../../components/icons'
import {
  getConversation,
  sendConversationMessage,
  type Message,
} from '../../lib/api'
import { useAuth } from '../../lib/auth'
import type { DashboardOutletContext } from './Layout'

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
  const {
    conversations,
    conversationsLoading,
    refreshConversations,
    startConversation,
  } = useOutletContext<DashboardOutletContext>()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [booting, setBooting] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retryKey, setRetryKey] = useState(0)
  const logRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (conversationId || conversationsLoading) return

    if (conversations.length > 0) {
      navigate(`/app/chat/${conversations[0].id}`, { replace: true })
      return
    }

    let cancelled = false
    async function createFirstConversation() {
      setBooting(true)
      const conversation = await startConversation()
      if (!conversation && !cancelled) {
        setError('Cash couldn’t start a conversation. Please try again.')
        setBooting(false)
      }
    }
    void createFirstConversation()
    return () => {
      cancelled = true
    }
  }, [
    conversationId,
    conversations,
    conversationsLoading,
    navigate,
    startConversation,
  ])

  useEffect(() => {
    if (!conversationId) return
    const activeConversationId = conversationId
    let cancelled = false

    async function loadConversation() {
      setError(null)
      setBooting(true)
      const data = await getConversation(activeConversationId)
      if (cancelled) return
      if (!data) {
        setMessages([])
        setError('This conversation couldn’t be loaded. It may no longer be available.')
      } else {
        setMessages(data.messages)
      }
      setBooting(false)
    }

    void loadConversation()
    return () => {
      cancelled = true
    }
  }, [conversationId, retryKey])

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, thinking])

  function autosize() {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`
  }

  async function send() {
    const text = input.trim()
    if (!text || thinking || !conversationId) return

    setInput('')
    setError(null)
    requestAnimationFrame(autosize)
    setMessages((current) => [
      ...current,
      { id: `tmp-${Date.now()}`, role: 'user', content: text, createdAt: '' },
    ])
    setThinking(true)

    try {
      const { reply } = await sendConversationMessage(conversationId, text)
      setMessages((current) => [
        ...current,
        { id: `assistant-${Date.now()}`, role: 'assistant', content: reply, createdAt: '' },
      ])
      await refreshConversations()
    } catch {
      setError('Your message didn’t send. Copy it and try again in a moment.')
      setInput(text)
      requestAnimationFrame(autosize)
    } finally {
      setThinking(false)
      requestAnimationFrame(() => textareaRef.current?.focus())
    }
  }

  function chooseStarter(starter: string) {
    setInput(starter)
    requestAnimationFrame(() => {
      autosize()
      textareaRef.current?.focus()
    })
  }

  const empty = messages.length === 0 && !thinking
  const firstName = user?.profile.firstName || 'there'

  return (
    <section className="chat" aria-label="Chat with Cash" aria-busy={thinking}>
      {error && messages.length > 0 && (
        <div className="chat-inline-error status-banner status-banner--error" role="alert">{error}</div>
      )}

      <div
        className="chat-log"
        ref={logRef}
        role="log"
        aria-live="polite"
        aria-relevant="additions"
      >
        {booting ? (
          <div className="chat-loading" role="status">
            <span className="spinner" aria-hidden="true" />
            <span>Loading conversation…</span>
          </div>
        ) : error && messages.length === 0 ? (
          <div className="state-panel state-panel--chat">
            <span className="state-panel__icon"><RefreshIcon /></span>
            <h2>Conversation unavailable</h2>
            <p>{error}</p>
            <button type="button" className="btn btn-primary" onClick={() => setRetryKey((current) => current + 1)}>
              <RefreshIcon /> Try again
            </button>
          </div>
        ) : empty ? (
          <div className="chat-greeting">
            <div className="chat-breadcrumb">
              <span>Thinking</span>
              <ChevronRightIcon />
            </div>
            <h1>Hey {firstName} — I’m Cash <span aria-hidden="true">⚡</span></h1>
            <p>
              I’m here to help with planning, research, managing your inbox and calendar,
              or simply thinking something through. What are you working on?
            </p>
            <span className="chat-greeting__mark" aria-hidden="true"><CashMark /></span>
            <div className="starters" aria-label="Suggested prompts">
              {STARTERS.map((starter) => (
                <button type="button" key={starter} className="starter" onClick={() => chooseStarter(starter)}>
                  {starter}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="chat-thread">
            <div className="chat-breadcrumb">
              <span>Thinking</span>
              <ChevronRightIcon />
            </div>
            {messages.map((message) => (
              <article key={message.id} className={`turn ${message.role}`}>
                <span className="avatar" aria-hidden="true">
                  {message.role === 'assistant' ? <CashMark /> : (user?.profile.firstName?.[0]?.toUpperCase() || 'Y')}
                </span>
                <div className="content">{message.content}</div>
              </article>
            ))}
            {thinking && (
              <div className="turn assistant">
                <span className="avatar" aria-hidden="true"><CashMark /></span>
                <div className="content typing" role="status" aria-label="Cash is thinking">
                  <span /><span /><span />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="composer-wrap">
        <div className="desktop-promo">
          <span className="desktop-promo__icon" aria-hidden="true"><MonitorIcon /></span>
          <span className="desktop-promo__copy">
            <b>Get the desktop app</b>
            <span>Computer access · faster workflows · native automation</span>
          </span>
          <button type="button" className="btn btn-primary btn-small" disabled title="Desktop app coming soon">
            <DownloadIcon /> Coming soon
          </button>
        </div>

        <form
          className="composer"
          aria-label="Message Cash"
          onSubmit={(event) => {
            event.preventDefault()
            void send()
          }}
        >
          <div className="composer-field">
            <label className="sr-only" htmlFor="chat-message">Message Cash</label>
            <textarea
              id="chat-message"
              name="message"
              ref={textareaRef}
              value={input}
              rows={1}
              placeholder="What are you working on?"
              disabled={booting || !conversationId}
              aria-describedby="composer-hint"
              onChange={(event) => {
                setInput(event.target.value)
                autosize()
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void send()
                }
              }}
            />
            <div className="composer-footer">
              <div className="composer-mode" id="composer-hint">
                <span className="composer-status-dot" aria-hidden="true" />
                <ShieldIcon />
                <SparklesIcon />
                <span>Balanced</span>
              </div>
              <div className="composer-actions">
                <button type="button" className="composer-action" aria-label="Attach a file" disabled>
                  <PaperclipIcon />
                </button>
                <button type="button" className="composer-action" aria-label="Use voice input" disabled>
                  <MicIcon />
                </button>
                <button
                  type="submit"
                  className="send-btn"
                  disabled={!input.trim() || thinking || booting || !conversationId}
                  aria-label={thinking ? 'Cash is responding' : 'Send message'}
                >
                  {thinking ? <span className="spinner spinner--button" aria-hidden="true" /> : <SendIcon />}
                </button>
              </div>
            </div>
          </div>
        </form>
      </div>
    </section>
  )
}
