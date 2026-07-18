import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import CashMark from '../../components/CashMark'
import ConfirmDialog from '../../components/ConfirmDialog'
import {
  ActivityIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
  EditIcon,
  GearIcon,
  GridIcon,
  LogOutIcon,
  PanelIcon,
  SearchIcon,
  TrashIcon,
} from '../../components/icons'
import {
  createConversation,
  deleteConversation,
  listConversations,
  type Conversation,
} from '../../lib/api'
import { useAuth } from '../../lib/auth'

export interface DashboardOutletContext {
  conversations: Conversation[]
  conversationsLoading: boolean
  refreshConversations: () => Promise<Conversation[]>
  startConversation: () => Promise<Conversation | null>
}

const NAVIGATION = [
  { to: '/app/chat', label: 'Cash', icon: CashMark, end: false },
  { to: '/app/integrations', label: 'Library', icon: GridIcon, end: false },
  { to: '/app', label: 'Activity', icon: ActivityIcon, end: true },
]

export default function DashboardLayout() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(() => window.localStorage.getItem('cash-sidebar') === 'collapsed')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationsLoading, setConversationsLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null)
  const [deleting, setDeleting] = useState(false)
  const creatingRef = useRef(false)

  const refreshConversations = useCallback(async () => {
    setConversationsLoading(true)
    const list = await listConversations()
    setConversations(list)
    setConversationsLoading(false)
    return list
  }, [])

  useEffect(() => {
    void refreshConversations()
  }, [refreshConversations])

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  function toggleSidebar() {
    if (window.innerWidth <= 900) {
      setMobileOpen((current) => !current)
      return
    }
    setCollapsed((current) => {
      const next = !current
      window.localStorage.setItem('cash-sidebar', next ? 'collapsed' : 'expanded')
      return next
    })
  }

  const startConversation = useCallback(async () => {
    if (creatingRef.current) return null
    creatingRef.current = true
    setCreating(true)
    try {
      const conversation = await createConversation()
      if (conversation) {
        await refreshConversations()
        navigate(`/app/chat/${conversation.id}`)
      }
      return conversation
    } finally {
      creatingRef.current = false
      setCreating(false)
    }
  }, [navigate, refreshConversations])

  async function confirmDelete() {
    if (!pendingDelete) return
    setDeleting(true)
    const deleted = await deleteConversation(pendingDelete.id)
    if (deleted) {
      const list = await refreshConversations()
      if (location.pathname === `/app/chat/${pendingDelete.id}`) {
        navigate(list.length ? `/app/chat/${list[0].id}` : '/app/chat', { replace: true })
      }
    }
    setDeleting(false)
    setPendingDelete(null)
  }

  async function handleSignOut() {
    setSigningOut(true)
    await signOut()
    navigate('/signin', { replace: true })
  }

  const currentConversation = conversations.find(
    (conversation) => location.pathname === `/app/chat/${conversation.id}`,
  )
  const utilityTitle = useMemo(() => {
    if (location.pathname.startsWith('/app/chat')) return currentConversation?.title || 'Cash & You'
    if (location.pathname.startsWith('/app/integrations')) return 'Library'
    if (location.pathname.startsWith('/app/settings')) return 'Settings'
    return 'Activity'
  }, [currentConversation?.title, location.pathname])

  const initials = (
    (user?.profile.firstName?.[0] || user?.email?.[0] || 'C') +
    (user?.profile.lastName?.[0] || '')
  ).toUpperCase()

  const outletContext: DashboardOutletContext = {
    conversations,
    conversationsLoading,
    refreshConversations,
    startConversation,
  }

  return (
    <div className={`app-shell${collapsed ? ' is-collapsed' : ''}${mobileOpen ? ' is-mobile-open' : ''}`}>
      <a className="skip-link" href="#app-content">Skip to main content</a>

      <header className="app-utility">
        <div className="app-utility__left">
          <button
            type="button"
            className="utility-button"
            aria-label={mobileOpen || !collapsed ? 'Collapse navigation' : 'Expand navigation'}
            aria-expanded={window.innerWidth <= 900 ? mobileOpen : !collapsed}
            onClick={toggleSidebar}
          >
            <PanelIcon />
          </button>
          <button type="button" className="utility-button" aria-label="Open Cash chat" onClick={() => navigate('/app/chat')}>
            <SearchIcon />
          </button>
          <button type="button" className="utility-button utility-button--history" aria-label="Go back" onClick={() => navigate(-1)}>
            <ChevronLeftIcon />
          </button>
          <button type="button" className="utility-button utility-button--history" aria-label="Go forward" onClick={() => navigate(1)}>
            <ChevronRightIcon />
          </button>
        </div>
        <button type="button" className="workspace-title" onClick={() => navigate('/app/chat')}>
          <span className="workspace-title__mark" aria-hidden="true"><CashMark /></span>
          <span>{utilityTitle}</span>
          <ChevronDownIcon />
        </button>
      </header>

      <button
        type="button"
        className="app-side-backdrop"
        aria-label="Close navigation"
        tabIndex={mobileOpen ? 0 : -1}
        onClick={() => setMobileOpen(false)}
      />

      <aside className="app-side" aria-label="Application navigation">
        <nav className="side-nav" aria-label="Primary navigation">
          {NAVIGATION.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              title={collapsed ? label : undefined}
              className={({ isActive }) => `side-link${label === 'Cash' ? ' side-link--cash' : ''}${isActive ? ' active' : ''}`}
            >
              <span className="side-link__icon"><Icon /></span>
              <span className="side-link__label">{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="side-divider" />

        <section className="side-conversations" aria-labelledby="conversation-list-title">
          <div className="side-section-heading">
            <h2 id="conversation-list-title">Conversations</h2>
            <button
              type="button"
              className="utility-button"
              aria-label="Start a new conversation"
              disabled={creating}
              onClick={() => void startConversation()}
            >
              {creating ? <span className="spinner spinner--button" aria-hidden="true" /> : <EditIcon />}
            </button>
          </div>

          <div className="side-conversation-list">
            {conversationsLoading && conversations.length === 0 ? (
              <div className="side-conversation-loading" aria-hidden="true">
                <span className="skeleton skeleton--line" />
                <span className="skeleton skeleton--line skeleton--short" />
              </div>
            ) : conversations.length === 0 ? (
              <p className="side-conversation-empty">No conversations yet.</p>
            ) : conversations.slice(0, 8).map((conversation) => {
              const active = location.pathname === `/app/chat/${conversation.id}`
              return (
                <div className={`side-conversation${active ? ' active' : ''}`} key={conversation.id}>
                  <button
                    type="button"
                    className="side-conversation__link"
                    aria-current={active ? 'page' : undefined}
                    onClick={() => navigate(`/app/chat/${conversation.id}`)}
                  >
                    {conversation.title || 'New conversation'}
                  </button>
                  <button
                    type="button"
                    className="side-conversation__action"
                    aria-label={`Delete ${conversation.title || 'conversation'}`}
                    onClick={() => setPendingDelete(conversation)}
                  >
                    <TrashIcon />
                  </button>
                </div>
              )
            })}
          </div>
        </section>

        <div className="side-collapsed-actions" aria-label="Conversation actions">
          <button type="button" className="side-link" title="New conversation" onClick={() => void startConversation()}>
            <EditIcon />
          </button>
          <button type="button" className="side-link" title="Recent conversations" onClick={() => setCollapsed(false)}>
            <ClockIcon />
          </button>
        </div>

        <div className="side-foot">
          <NavLink
            to="/app/settings"
            title={collapsed ? 'Preferences' : undefined}
            className={({ isActive }) => `side-link${isActive ? ' active' : ''}`}
          >
            <span className="side-link__icon"><GearIcon /></span>
            <span className="side-link__label">Preferences</span>
          </NavLink>

          <div className="side-account">
            <span className="side-avatar" aria-hidden="true">{initials}</span>
            <span className="side-account__copy">
              <b>{user?.profile.firstName || 'You'}</b>
              <span>{user?.email}</span>
            </span>
            <button
              type="button"
              className="utility-button"
              aria-label="Sign out"
              title="Sign out"
              disabled={signingOut}
              onClick={() => void handleSignOut()}
            >
              {signingOut ? <span className="spinner spinner--button" aria-hidden="true" /> : <LogOutIcon />}
            </button>
          </div>
        </div>
      </aside>

      <main
        className={`app-main${location.pathname.startsWith('/app/chat') ? ' app-main--chat' : ''}`}
        id="app-content"
      >
        <Outlet context={outletContext} />
      </main>

      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete this conversation?"
        description="This removes the conversation and its messages. This action can’t be undone."
        confirmLabel="Delete conversation"
        tone="danger"
        busy={deleting}
        onClose={() => setPendingDelete(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  )
}
