import { useEffect, useRef, useState } from 'react'
import CashMark from '../../components/CashMark'
import { SendIcon } from '../../components/icons'
import { sendChat } from '../../lib/api'
import { useAuth } from '../../lib/auth'

interface Msg { role: 'me' | 'cash'; text: string }

export default function Chat() {
  const { user } = useAuth()
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [msgs, thinking])

  async function send() {
    const text = input.trim()
    if (!text || thinking) return
    setInput('')
    setMsgs((m) => [...m, { role: 'me', text }])
    setThinking(true)
    const { reply } = await sendChat(text)
    setThinking(false)
    setMsgs((m) => [...m, { role: 'cash', text: reply }])
  }

  return (
    <div className="chat">
      <div className="app-head">
        <h1>Chat</h1>
      </div>
      <div className="chat-log" ref={logRef}>
        {msgs.length === 0 && !thinking && (
          <div className="chat-empty">
            <span className="mark"><CashMark /></span>
            <h2>Hey {user?.profile.firstName || 'there'} 👋</h2>
            <p>I'm Cash — your cat who runs the boring stuff. Ask me about your day, your calendar,
              a reminder, or just say hi. Same brain everywhere you talk to me.</p>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={'msg ' + (m.role === 'me' ? 'me' : '')}>
            <span className="who-mark">{m.role === 'cash' ? <CashMark /> : (user?.profile.firstName?.[0] || 'Y')}</span>
            <div className="bubble">{m.text}</div>
          </div>
        ))}
        {thinking && (
          <div className="msg">
            <span className="who-mark"><CashMark /></span>
            <div className="bubble typing"><span></span><span></span><span></span></div>
          </div>
        )}
      </div>
      <div className="chat-input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') send() }}
          placeholder="Message Cash…"
          autoFocus
        />
        <button className="btn btn-primary" onClick={send} aria-label="Send">
          <SendIcon />
        </button>
      </div>
    </div>
  )
}
