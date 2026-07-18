import { useState } from 'react'
import { Link } from 'react-router-dom'
import CashMark from '../../components/CashMark'
import PageHeader from '../../components/PageHeader'
import {
  ActivityIcon,
  ChatIcon,
  ClockIcon,
  RefreshIcon,
  SparklesIcon,
  XIcon,
} from '../../components/icons'
import { useAuth } from '../../lib/auth'

interface FeedItem {
  id: string
  icon: 'cash' | 'calendar' | 'chat'
  title: string
  text: string
  time: string
}

const STARTER_FEED: FeedItem[] = [
  {
    id: 'f1',
    icon: 'cash',
    title: 'Cash is on the clock',
    text: "I'm watching your calendar, inbox, and reminders. I'll surface anything that needs you here.",
    time: 'Just now',
  },
  {
    id: 'f2',
    icon: 'calendar',
    title: 'Connect your calendar',
    text: 'Hook up Google Calendar and I can flag conflicts and brief you every morning.',
    time: 'Tip',
  },
  {
    id: 'f3',
    icon: 'chat',
    title: 'Say hi in Chat',
    text: "Ask me anything — same brain and memory as Telegram. I don't forget.",
    time: 'Tip',
  },
]

const SCHEDULES = [
  { Icon: ClockIcon, title: 'Heartbeat', sub: 'Hourly — I check for anything worth a nudge', badge: 'On' },
  { Icon: SparklesIcon, title: 'Morning brief', sub: 'Your day, conflicts, and reminders — first thing', badge: 'On' },
  { Icon: RefreshIcon, title: 'Follow-up sweep', sub: 'I chase the things you said you’d do', badge: 'On' },
]

const FEED_ICONS = {
  cash: CashMark,
  calendar: ActivityIcon,
  chat: ChatIcon,
}

export default function Activity() {
  const { user } = useAuth()
  const [tab, setTab] = useState<'notifications' | 'schedules'>('notifications')
  const [feed, setFeed] = useState(STARTER_FEED)
  const [read, setRead] = useState<Record<string, boolean>>({})

  const unreadCount = feed.filter((item) => !read[item.id]).length

  return (
    <>
      <PageHeader
        title="Activity"
        description="Updates, reminders, and the routines Cash is running for you."
      />

      <div className="app-body">
        <div className="activity">
          <div className="tabs" role="tablist" aria-label="Activity views">
            <button
              id="notifications-tab"
              type="button"
              role="tab"
              className={`tab${tab === 'notifications' ? ' on' : ''}`}
              aria-selected={tab === 'notifications'}
              aria-controls="notifications-panel"
              onClick={() => setTab('notifications')}
            >
              Notifications
              {unreadCount > 0 && <span className="tab-count" aria-label={`${unreadCount} unread`}>{unreadCount}</span>}
            </button>
            <button
              id="schedules-tab"
              type="button"
              role="tab"
              className={`tab${tab === 'schedules' ? ' on' : ''}`}
              aria-selected={tab === 'schedules'}
              aria-controls="schedules-panel"
              onClick={() => setTab('schedules')}
            >
              Schedules
            </button>
          </div>

          {tab === 'notifications' ? (
            <section
              id="notifications-panel"
              role="tabpanel"
              aria-labelledby="notifications-tab"
              tabIndex={0}
              className="tab-panel"
            >
              <div className="feed-toolbar">
                <p>{unreadCount ? `${unreadCount} unread update${unreadCount === 1 ? '' : 's'}` : 'You’re all caught up'}</p>
                <div className="feed-actions">
                  <button
                    type="button"
                    disabled={unreadCount === 0}
                    onClick={() => setRead(Object.fromEntries(feed.map((item) => [item.id, true])))}
                  >
                    Mark all read
                  </button>
                  <button type="button" disabled={feed.length === 0} onClick={() => setFeed([])}>Clear all</button>
                </div>
              </div>

              {feed.length === 0 ? (
                <div className="empty-state">
                  <span className="empty-state__icon"><CashMark /></span>
                  <h2>Nothing needs your attention</h2>
                  <p>Cash will surface new reminders and useful updates here.</p>
                </div>
              ) : (
                <div className="feed-list" aria-live="polite">
                  {feed.map((item) => {
                    const FeedIcon = FEED_ICONS[item.icon]
                    return (
                      <article
                        key={item.id}
                        className={`feed-item${read[item.id] ? ' feed-item--read' : ''}`}
                      >
                        <span className="fi-icon" aria-hidden="true"><FeedIcon /></span>
                        <div className="fi-body">
                          <div className="fi-title-row">
                            <h2 className="fi-title">{item.title}</h2>
                            {!read[item.id] && <span className="unread-dot"><span className="sr-only">Unread</span></span>}
                          </div>
                          <p className="fi-text">{item.text}</p>
                          <span className="fi-time">{item.time}</span>
                        </div>
                        <button
                          type="button"
                          className="icon-button fi-close"
                          onClick={() => setFeed((current) => current.filter((entry) => entry.id !== item.id))}
                          aria-label={`Dismiss ${item.title}`}
                        >
                          <XIcon />
                        </button>
                      </article>
                    )
                  })}
                </div>
              )}

              <p className="activity-cta">
                Want a faster answer? <Link className="inline-link" to="/app/chat">Ask Cash in chat <span aria-hidden="true">→</span></Link>
              </p>
            </section>
          ) : (
            <section
              id="schedules-panel"
              role="tabpanel"
              aria-labelledby="schedules-tab"
              tabIndex={0}
              className="tab-panel"
            >
              <p className="section-note">Recurring tasks Cash handles automatically. More scheduling controls are coming soon.</p>

              <div className="sched-group">
                <h2>System tasks</h2>
                <div className="schedule-list">
                  {SCHEDULES.map(({ Icon, ...schedule }) => (
                    <article className="sched-row" key={schedule.title}>
                      <span className="sr-emoji" aria-hidden="true"><Icon /></span>
                      <div className="sr-body">
                        <h3 className="sr-title">{schedule.title}</h3>
                        <p className="sr-sub">{schedule.sub}</p>
                      </div>
                      <span className="status-chip status-chip--success"><span className="status-chip__dot" />{schedule.badge}</span>
                    </article>
                  ))}
                </div>
              </div>

              <div className="sched-group">
                <h2>Your schedules</h2>
                <div className="empty-state empty-state--compact">
                  <h3>No personal schedules yet</h3>
                  <p>
                    Tell Cash “remind me every morning to…” in <Link className="inline-link" to="/app/chat">chat</Link> and it will appear here,
                    {` ${user?.profile.firstName || 'friend'}`}.
                  </p>
                </div>
              </div>
            </section>
          )}
        </div>
      </div>
    </>
  )
}
