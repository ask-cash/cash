import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../lib/auth'

// The dashboard's Home / Activity page (blueprint §7.3): a two-tab surface —
// Notifications (Cash's feed of recaps + nudges) and Schedules (what Cash runs
// on a timer). Structure mirrors the blueprint; content is in Cash's voice.

interface FeedItem { id: string; emoji: string; title: string; text: string; time: string }

const STARTER_FEED: FeedItem[] = [
  { id: 'f1', emoji: '🐈‍⬛', title: 'Cash is on the clock', text: "I'm watching your calendar, inbox, and reminders. I'll surface anything that needs you here.", time: 'just now' },
  { id: 'f2', emoji: '📅', title: 'Connect your calendar', text: 'Hook up Google Calendar and I can flag conflicts and brief you every morning.', time: 'tip' },
  { id: 'f3', emoji: '💬', title: 'Say hi in Chat', text: "Ask me anything — same brain and memory as Telegram. I don't forget.", time: 'tip' },
]

const SCHEDULES = {
  system: [
    { emoji: '💓', title: 'Heartbeat', sub: 'Hourly — I check for anything worth a nudge', badge: 'On' },
    { emoji: '🌅', title: 'Morning brief', sub: 'Your day, conflicts, and reminders — first thing', badge: 'On' },
    { emoji: '🧹', title: 'Follow-up sweep', sub: 'I chase the things you said you’d do', badge: 'On' },
  ],
}

export default function Activity() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [tab, setTab] = useState<'notifications' | 'schedules'>('notifications')
  const [feed, setFeed] = useState(STARTER_FEED)
  const [read, setRead] = useState<Record<string, boolean>>({})

  const unread = feed.some((f) => !read[f.id])

  return (
    <>
      <div className="app-head">
        <h1 className="serif" style={{ fontSize: 26 }}>Activity</h1>
      </div>
      <div className="app-body">
        <div className="activity">
          <div className="tabs">
            <button className={'tab' + (tab === 'notifications' ? ' on' : '')} onClick={() => setTab('notifications')}>
              Notifications{unread && tab !== 'notifications' && <span className="dot" />}
            </button>
            <button className={'tab' + (tab === 'schedules' ? ' on' : '')} onClick={() => setTab('schedules')}>
              Schedules
            </button>
          </div>

          {tab === 'notifications' ? (
            <>
              <div className="feed-actions">
                <button onClick={() => setRead(Object.fromEntries(feed.map((f) => [f.id, true])))}>Mark all as read</button>
                <button onClick={() => setFeed([])}>Clear all</button>
              </div>
              {feed.length === 0 ? (
                <div className="feed-empty">
                  <p>All clear. 😺 I'll pop things here when they need you.</p>
                </div>
              ) : (
                feed.map((f) => (
                  <div key={f.id} className={'feed-item' + (read[f.id] ? ' read' : '')}>
                    <span className="fi-icon">{f.emoji}</span>
                    <div className="fi-body">
                      <div className="fi-title">{f.title}</div>
                      <div className="fi-text">{f.text}</div>
                      <div className="fi-time">{f.time}</div>
                    </div>
                    <button className="fi-close" onClick={() => setFeed((s) => s.filter((x) => x.id !== f.id))} aria-label="Dismiss">×</button>
                  </div>
                ))
              )}
              <p className="section-note" style={{ marginTop: 18 }}>
                Want faster action? <a style={{ cursor: 'pointer', color: 'var(--ink)' }} onClick={() => navigate('/app/chat')}>Ask Cash in chat →</a>
              </p>
            </>
          ) : (
            <>
              <p className="section-note">The things Cash runs for you on a timer. More scheduling controls are coming soon.</p>
              <div className="sched-group">
                <h3>System tasks</h3>
                {SCHEDULES.system.map((s) => (
                  <div className="sched-row" key={s.title}>
                    <span className="sr-emoji">{s.emoji}</span>
                    <div className="sr-body">
                      <div className="sr-title">{s.title}</div>
                      <div className="sr-sub">{s.sub}</div>
                    </div>
                    <span className="sr-badge">{s.badge}</span>
                  </div>
                ))}
              </div>
              <div className="sched-group">
                <h3>Your schedules</h3>
                <div className="feed-empty" style={{ padding: '24px 0' }}>
                  <p>No schedules yet, {user?.profile.firstName || 'friend'}. Tell me “remind me every morning to…” in chat and I'll set one up.</p>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}
