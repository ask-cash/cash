import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import CashMark from '../../components/CashMark'
import ConfirmDialog from '../../components/ConfirmDialog'
import PageHeader from '../../components/PageHeader'
import {
  ActivityIcon,
  ChatIcon,
  CheckIcon,
  ClockIcon,
  RefreshIcon,
  SparklesIcon,
  XIcon,
} from '../../components/icons'
import {
  clearActivity,
  deleteActivity,
  getActivity,
  markActivityRead,
  markAllActivityRead,
  type ActivityItem,
} from '../../lib/api'
import { useAuth } from '../../lib/auth'

const ACTIVITY_POLL_BASE_MS = 15_000
const ACTIVITY_POLL_MAX_MS = 120_000
const ACTIVITY_POLL_RETRY_MS = 750
const ACTIVITY_IMMEDIATE_DEDUPLICATION_MS = 1_000
const ACTIVITY_POLL_JITTER = 0.25
const activityDateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
})

const SCHEDULES = [
  { Icon: ClockIcon, title: 'Heartbeat', sub: 'Hourly — I check for anything worth a nudge', badge: 'On' },
  { Icon: SparklesIcon, title: 'Morning brief', sub: 'Your day, conflicts, and reminders — first thing', badge: 'On' },
  { Icon: RefreshIcon, title: 'Follow-up sweep', sub: 'I chase the things you said you’d do', badge: 'On' },
]

interface Notice {
  tone: 'success' | 'error'
  message: string
}

type LoadMode = 'initial' | 'manual' | 'poll'
type LoadResult = 'success' | 'failure' | 'aborted' | 'skipped'

function activityPollDelay(failureCount: number): number {
  const exponentialDelay = ACTIVITY_POLL_BASE_MS * (2 ** Math.min(failureCount, 5))
  const jitterCenter = Math.min(
    exponentialDelay,
    ACTIVITY_POLL_MAX_MS / (1 + ACTIVITY_POLL_JITTER),
  )
  const jitter = 1 - ACTIVITY_POLL_JITTER + (Math.random() * ACTIVITY_POLL_JITTER * 2)
  return Math.round(jitterCenter * jitter)
}

function iconForActivity(type: string) {
  const normalized = type.toLowerCase()
  if (normalized.includes('reminder') || normalized.includes('schedule')) return ClockIcon
  if (normalized.includes('calendar')) return ActivityIcon
  if (normalized.includes('chat') || normalized.includes('message')) return ChatIcon
  return CashMark
}

function formatActivityTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Recently'

  const elapsed = Date.now() - date.getTime()
  if (elapsed >= -15_000 && elapsed < 45_000) return 'Just now'
  if (elapsed >= 0 && elapsed < 60 * 60_000) {
    const minutes = Math.max(1, Math.floor(elapsed / 60_000))
    return `${minutes} min ago`
  }
  if (elapsed >= 0 && elapsed < 24 * 60 * 60_000) {
    const hours = Math.max(1, Math.floor(elapsed / (60 * 60_000)))
    return `${hours} hr${hours === 1 ? '' : 's'} ago`
  }

  return activityDateTimeFormatter.format(date)
}

export default function Activity() {
  const { user } = useAuth()
  const [tab, setTab] = useState<'notifications' | 'schedules'>('notifications')
  const [feed, setFeed] = useState<ActivityItem[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [liveStatus, setLiveStatus] = useState('')
  const [pendingIds, setPendingIds] = useState<Set<string>>(() => new Set())
  const [bulkAction, setBulkAction] = useState<'read' | 'clear' | null>(null)
  const [clearDialogOpen, setClearDialogOpen] = useState(false)
  const requestIdRef = useRef(0)
  const requestsInFlightRef = useRef(0)
  const pollFailuresRef = useRef(0)
  const manualRefreshRef = useRef<(() => void) | null>(null)
  const knownItemIdsRef = useRef<Set<string>>(new Set())
  const hasLoadedRef = useRef(false)
  const mutationsRef = useRef(0)

  const loadFeed = useCallback(async (
    mode: LoadMode,
    signal?: AbortSignal,
  ): Promise<LoadResult> => {
    if (
      requestsInFlightRef.current > 0
      || (mode === 'poll' && mutationsRef.current > 0)
    ) return 'skipped'

    const requestId = ++requestIdRef.current
    requestsInFlightRef.current += 1
    if (!hasLoadedRef.current) setLoading(true)
    else if (mode === 'manual') setRefreshing(true)

    try {
      const next = await getActivity(signal)
      if (requestId !== requestIdRef.current) return 'skipped'
      const newItemCount = hasLoadedRef.current
        ? next.items.filter((item) => !knownItemIdsRef.current.has(item.id)).length
        : 0
      setFeed(next.items)
      setUnreadCount(next.unreadCount)
      setLoadError(null)
      knownItemIdsRef.current = new Set(next.items.map((item) => item.id))
      if (mode === 'poll' && newItemCount > 0) {
        setLiveStatus(`${newItemCount} new activity update${newItemCount === 1 ? '' : 's'}.`)
      } else if (mode === 'manual') {
        setLiveStatus(`Activity refreshed. ${next.unreadCount} unread update${next.unreadCount === 1 ? '' : 's'}.`)
      }
      hasLoadedRef.current = true
      pollFailuresRef.current = 0
      return 'success'
    } catch (error) {
      if ((error as Error).name === 'AbortError') return 'aborted'
      if (requestId !== requestIdRef.current) return 'skipped'
      pollFailuresRef.current = Math.min(pollFailuresRef.current + 1, 5)
      const message = error instanceof Error
        ? error.message
        : 'Cash couldn’t load your activity. Check your connection and try again.'
      if (!hasLoadedRef.current) setLoadError(message)
      else if (mode === 'manual') setNotice({ tone: 'error', message })
      return 'failure'
    } finally {
      requestsInFlightRef.current = Math.max(0, requestsInFlightRef.current - 1)
      if (requestId === requestIdRef.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    let activeController: AbortController | null = null
    let queuedMode: LoadMode | null = null
    let lastImmediateRefreshAt = 0

    function clearTimer() {
      if (timer === undefined) return
      window.clearTimeout(timer)
      timer = undefined
    }

    function scheduleNext() {
      clearTimer()
      if (stopped || document.visibilityState !== 'visible') return
      timer = window.setTimeout(
        () => void runPoll('poll'),
        activityPollDelay(pollFailuresRef.current),
      )
    }

    function retryQueuedRequest() {
      clearTimer()
      if (stopped || document.visibilityState !== 'visible' || !queuedMode) return
      timer = window.setTimeout(() => {
        timer = undefined
        if (requestsInFlightRef.current > 0) {
          retryQueuedRequest()
          return
        }
        const nextMode = queuedMode
        queuedMode = null
        if (nextMode) void runPoll(nextMode)
      }, ACTIVITY_POLL_RETRY_MS + Math.round(Math.random() * 250))
    }

    async function runPoll(mode: LoadMode) {
      if (stopped || document.visibilityState !== 'visible') return
      activeController = new AbortController()
      const result = await loadFeed(mode, activeController.signal)
      activeController = null
      if (stopped || document.visibilityState !== 'visible') return

      if (queuedMode) {
        clearTimer()
        const nextMode = queuedMode
        queuedMode = null
        void runPoll(nextMode)
        return
      }
      if (result === 'skipped') {
        queuedMode = mode
        retryQueuedRequest()
        return
      }
      scheduleNext()
    }

    function requestImmediate(mode: LoadMode, resetBackoff: boolean) {
      if (stopped || document.visibilityState !== 'visible') return
      if (resetBackoff) {
        pollFailuresRef.current = 0
        const now = Date.now()
        if (now - lastImmediateRefreshAt < ACTIVITY_IMMEDIATE_DEDUPLICATION_MS) return
        lastImmediateRefreshAt = now
      }
      clearTimer()
      if (requestsInFlightRef.current > 0) {
        if (mode === 'manual' || queuedMode === null) queuedMode = mode
        retryQueuedRequest()
        return
      }
      void runPoll(mode)
    }

    function handleVisibilityChange() {
      if (document.visibilityState !== 'visible') {
        clearTimer()
        queuedMode = null
        activeController?.abort()
        return
      }
      requestImmediate('poll', true)
    }

    const handleFocus = () => requestImmediate('poll', true)
    manualRefreshRef.current = () => requestImmediate('manual', false)
    if (document.visibilityState === 'visible') requestImmediate('initial', true)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('focus', handleFocus)

    return () => {
      stopped = true
      clearTimer()
      queuedMode = null
      activeController?.abort()
      manualRefreshRef.current = null
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('focus', handleFocus)
    }
  }, [loadFeed])

  function refreshFeed() {
    manualRefreshRef.current?.()
  }

  function beginItemMutation(id: string) {
    requestIdRef.current += 1
    mutationsRef.current += 1
    setRefreshing(false)
    setPendingIds((current) => new Set(current).add(id))
  }

  function endItemMutation(id: string) {
    mutationsRef.current = Math.max(0, mutationsRef.current - 1)
    setPendingIds((current) => {
      const next = new Set(current)
      next.delete(id)
      return next
    })
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    let nextTab: 'notifications' | 'schedules' | null = null
    if (event.key === 'ArrowLeft' || event.key === 'Home') nextTab = 'notifications'
    if (event.key === 'ArrowRight' || event.key === 'End') nextTab = 'schedules'
    if (!nextTab) return
    event.preventDefault()
    setTab(nextTab)
    window.requestAnimationFrame(() => {
      document.getElementById(`${nextTab}-tab`)?.focus()
    })
  }

  async function readItem(item: ActivityItem) {
    if (item.readAt || pendingIds.has(item.id) || bulkAction) return
    const optimisticReadAt = new Date().toISOString()
    beginItemMutation(item.id)
    setFeed((current) => current.map((entry) => (
      entry.id === item.id ? { ...entry, readAt: optimisticReadAt } : entry
    )))
    setUnreadCount((current) => Math.max(0, current - 1))

    try {
      await markActivityRead(item.id)
      setLiveStatus(`${item.title} marked as read.`)
    } catch (error) {
      setFeed((current) => current.map((entry) => (
        entry.id === item.id && entry.readAt === optimisticReadAt
          ? { ...entry, readAt: item.readAt }
          : entry
      )))
      setUnreadCount((current) => current + 1)
      setNotice({
        tone: 'error',
        message: error instanceof Error ? error.message : 'This update could not be marked as read.',
      })
    } finally {
      endItemMutation(item.id)
    }
  }

  async function dismissItem(item: ActivityItem) {
    if (pendingIds.has(item.id) || bulkAction) return
    const itemIndex = feed.findIndex((entry) => entry.id === item.id)
    beginItemMutation(item.id)
    setFeed((current) => current.filter((entry) => entry.id !== item.id))
    if (!item.readAt) setUnreadCount((current) => Math.max(0, current - 1))

    try {
      await deleteActivity(item.id)
      setLiveStatus(`${item.title} dismissed.`)
    } catch (error) {
      setFeed((current) => {
        if (current.some((entry) => entry.id === item.id)) return current
        const next = [...current]
        next.splice(Math.max(0, Math.min(itemIndex, next.length)), 0, item)
        return next
      })
      if (!item.readAt) setUnreadCount((current) => current + 1)
      setNotice({
        tone: 'error',
        message: error instanceof Error ? error.message : 'This update could not be dismissed.',
      })
    } finally {
      endItemMutation(item.id)
    }
  }

  async function readAll() {
    if (unreadCount === 0 || bulkAction || pendingIds.size > 0) return
    const previousFeed = feed
    const previousUnreadCount = unreadCount
    const optimisticReadAt = new Date().toISOString()
    requestIdRef.current += 1
    mutationsRef.current += 1
    setRefreshing(false)
    setBulkAction('read')
    setFeed((current) => current.map((item) => (
      item.readAt ? item : { ...item, readAt: optimisticReadAt }
    )))
    setUnreadCount(0)

    try {
      await markAllActivityRead()
      setLiveStatus('All activity marked as read.')
    } catch (error) {
      setFeed(previousFeed)
      setUnreadCount(previousUnreadCount)
      setNotice({
        tone: 'error',
        message: error instanceof Error ? error.message : 'Your updates could not be marked as read.',
      })
    } finally {
      mutationsRef.current = Math.max(0, mutationsRef.current - 1)
      setBulkAction(null)
    }
  }

  async function clearAll() {
    if (feed.length === 0 || bulkAction || pendingIds.size > 0) return
    const previousFeed = feed
    const previousUnreadCount = unreadCount
    requestIdRef.current += 1
    mutationsRef.current += 1
    setRefreshing(false)
    setBulkAction('clear')

    try {
      await clearActivity()
      setFeed([])
      setUnreadCount(0)
      setClearDialogOpen(false)
      setNotice({ tone: 'success', message: 'Updates cleared. Your scheduled reminders remain active.' })
    } catch (error) {
      setFeed(previousFeed)
      setUnreadCount(previousUnreadCount)
      setClearDialogOpen(false)
      setNotice({
        tone: 'error',
        message: error instanceof Error ? error.message : 'Your activity could not be cleared.',
      })
    } finally {
      mutationsRef.current = Math.max(0, mutationsRef.current - 1)
      setBulkAction(null)
    }
  }

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
              tabIndex={tab === 'notifications' ? 0 : -1}
              onClick={() => setTab('notifications')}
              onKeyDown={handleTabKeyDown}
            >
              Notifications
              {unreadCount > 0 && (
                <span className="tab-count" aria-label={`${unreadCount} unread`}>
                  {unreadCount > 99 ? '99+' : unreadCount}
                </span>
              )}
            </button>
            <button
              id="schedules-tab"
              type="button"
              role="tab"
              className={`tab${tab === 'schedules' ? ' on' : ''}`}
              aria-selected={tab === 'schedules'}
              aria-controls="schedules-panel"
              tabIndex={tab === 'schedules' ? 0 : -1}
              onClick={() => setTab('schedules')}
              onKeyDown={handleTabKeyDown}
            >
              Schedules
            </button>
          </div>

          {notice && (
            <div
              className={`status-banner status-banner--${notice.tone} status-banner--dismissible`}
              role={notice.tone === 'error' ? 'alert' : 'status'}
            >
              <span>{notice.message}</span>
              <button type="button" className="icon-button" aria-label="Dismiss message" onClick={() => setNotice(null)}>
                <XIcon />
              </button>
            </div>
          )}
          <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{liveStatus}</p>

          {tab === 'notifications' ? (
            <section
              id="notifications-panel"
              role="tabpanel"
              aria-labelledby="notifications-tab"
              tabIndex={0}
              className="tab-panel"
            >
              {!loading && !loadError && (
                <div className="feed-toolbar">
                  <p>{unreadCount ? `${unreadCount} unread update${unreadCount === 1 ? '' : 's'}` : 'You’re all caught up'}</p>
                  <div className="feed-actions">
                    <button
                      type="button"
                      disabled={refreshing || !!bulkAction || pendingIds.size > 0}
                      onClick={refreshFeed}
                    >
                      {refreshing
                        ? <span className="spinner spinner--button" aria-hidden="true" />
                        : <RefreshIcon />}
                      Refresh
                    </button>
                    <button
                      type="button"
                      disabled={unreadCount === 0 || !!bulkAction || pendingIds.size > 0}
                      onClick={() => void readAll()}
                    >
                      {bulkAction === 'read' && <span className="spinner spinner--button" aria-hidden="true" />}
                      Mark all read
                    </button>
                    <button
                      type="button"
                      disabled={feed.length === 0 || !!bulkAction || pendingIds.size > 0}
                      onClick={() => setClearDialogOpen(true)}
                    >
                      Clear all
                    </button>
                  </div>
                </div>
              )}

              {loading ? (
                <div className="activity-loading" role="status" aria-label="Loading activity" aria-busy="true">
                  {[0, 1, 2].map((item) => (
                    <div className="activity-loading__item" key={item}>
                      <span className="skeleton activity-loading__icon" />
                      <span className="activity-loading__copy">
                        <span className="skeleton skeleton--line" />
                        <span className="skeleton skeleton--line skeleton--short" />
                        <span className="skeleton activity-loading__time" />
                      </span>
                    </div>
                  ))}
                </div>
              ) : loadError ? (
                <div className="state-panel activity-state-panel" role="alert">
                  <span className="state-panel__icon"><RefreshIcon /></span>
                  <h2>Your activity didn’t load</h2>
                  <p>{loadError}</p>
                  <button type="button" className="btn btn-primary" onClick={refreshFeed}>
                    <RefreshIcon /> Try again
                  </button>
                </div>
              ) : feed.length === 0 ? (
                <div className="empty-state">
                  <span className="empty-state__icon"><CashMark /></span>
                  <h2>Nothing needs your attention</h2>
                  <p>New reminders and useful updates from Cash will appear here.</p>
                </div>
              ) : (
                <div className="feed-list" aria-busy={refreshing}>
                  {feed.map((item) => {
                    const FeedIcon = iconForActivity(item.type)
                    const pending = pendingIds.has(item.id)
                    return (
                      <article
                        key={item.id}
                        className={`feed-item${item.readAt ? ' feed-item--read' : ''}`}
                      >
                        <span className="fi-icon" aria-hidden="true"><FeedIcon /></span>
                        <div className="fi-body">
                          <div className="fi-title-row">
                            <h2 className="fi-title">{item.title}</h2>
                            {!item.readAt && <span className="unread-dot"><span className="sr-only">Unread</span></span>}
                          </div>
                          <p className="fi-text">{item.text}</p>
                          <time className="fi-time" dateTime={item.createdAt}>{formatActivityTime(item.createdAt)}</time>
                        </div>
                        <div className="fi-actions">
                          {!item.readAt && (
                            <button
                              type="button"
                              className="icon-button fi-action"
                              disabled={pending || !!bulkAction}
                              onClick={() => void readItem(item)}
                              aria-label={`Mark ${item.title} as read`}
                            >
                              <CheckIcon />
                            </button>
                          )}
                          <button
                            type="button"
                            className="icon-button fi-action"
                            disabled={pending || !!bulkAction}
                            onClick={() => void dismissItem(item)}
                            aria-label={`Dismiss ${item.title}`}
                          >
                            {pending ? <span className="spinner spinner--button" aria-hidden="true" /> : <XIcon />}
                          </button>
                        </div>
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

      <ConfirmDialog
        open={clearDialogOpen}
        title="Clear activity history?"
        description="This removes the updates currently shown here. Future scheduled reminders remain active."
        confirmLabel="Clear activity"
        tone="danger"
        busy={bulkAction === 'clear'}
        onConfirm={() => void clearAll()}
        onClose={() => {
          if (!bulkAction) setClearDialogOpen(false)
        }}
      />
    </>
  )
}
