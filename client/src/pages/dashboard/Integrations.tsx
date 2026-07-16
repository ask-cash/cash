import { useCallback, useEffect, useMemo, useState } from 'react'
import CashMark from '../../components/CashMark'
import ConfirmDialog from '../../components/ConfirmDialog'
import PageHeader from '../../components/PageHeader'
import { RefreshIcon, SparklesIcon, XIcon } from '../../components/icons'
import { logoSrc } from '../../data/logos'
import { disconnectConnector, fetchConnectors, type Connector } from '../../lib/api'

const BLURB: Record<string, string> = {
  google_calendar: 'See and manage your schedule, resolve conflicts, and get a morning brief.',
  gmail: 'Triage and summarise your inbox.',
  outlook: 'Bring your Outlook calendar into one clear view.',
  discord: 'Message Cash from Discord with one shared memory.',
  telegram: 'Chat with Cash from Telegram with the same context.',
  slack: 'Bring Cash into your workspace channels and direct messages.',
  notion: 'Read and write your workspace documents.',
  hubspot: 'Keep useful CRM context close at hand.',
  linear: 'Track issues and surface shipping updates.',
  twitter: 'Get a useful summary of your timeline.',
}

const MAP_ORDER = ['google_calendar', 'gmail', 'telegram', 'discord', 'slack', 'notion']

interface Notice {
  tone: 'success' | 'error'
  message: string
}

interface DialogState {
  mode: 'disconnect' | 'hint'
  connector: Connector
}

type LibraryView = 'identity' | 'integrations' | 'skills'

function initialNotice(): Notice | null {
  const params = new URLSearchParams(window.location.search)
  const connected = params.get('connected')
  if (connected) {
    return { tone: 'success', message: `Connected ${connected.replaceAll('-', ' ')}. You’re all set.` }
  }
  if (params.get('error')) {
    return { tone: 'error', message: 'We couldn’t finish connecting that service. Please try again.' }
  }
  return null
}

export default function Integrations() {
  const [connectors, setConnectors] = useState<Connector[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionId, setActionId] = useState<string | null>(null)
  const [notice, setNotice] = useState<Notice | null>(initialNotice)
  const [dialog, setDialog] = useState<DialogState | null>(null)
  const [view, setView] = useState<LibraryView>(() => {
    const params = new URLSearchParams(window.location.search)
    return params.has('connected') || params.has('error') ? 'integrations' : 'identity'
  })

  const load = useCallback(async (showLoader = true) => {
    if (showLoader) setLoading(true)
    setLoadError(null)
    const nextConnectors = await fetchConnectors()
    if (nextConnectors.length === 0) {
      setLoadError('Cash couldn’t load your integrations. Check your connection and try again.')
    } else {
      setConnectors(nextConnectors)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()

    const url = new URL(window.location.href)
    if (url.searchParams.has('connected') || url.searchParams.has('error')) {
      url.searchParams.delete('connected')
      url.searchParams.delete('error')
      window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
    }
  }, [load])

  function connect(connector: Connector) {
    if (connector.id === 'google_calendar') {
      setActionId(connector.id)
      window.location.href = '/api/connect/google/start'
      return
    }
    setDialog({ mode: 'hint', connector })
  }

  async function confirmDialog() {
    if (!dialog) return
    if (dialog.mode === 'hint') {
      setDialog(null)
      return
    }

    const connector = dialog.connector
    setActionId(connector.id)
    const disconnected = await disconnectConnector(connector.id)
    if (disconnected) {
      setNotice({ tone: 'success', message: `${connector.title} was disconnected.` })
      await load(false)
      setDialog(null)
    } else {
      setNotice({ tone: 'error', message: `We couldn’t disconnect ${connector.title}. Please try again.` })
    }
    setActionId(null)
  }

  const available = connectors.filter((connector) => connector.available)
  const soon = connectors.filter((connector) => !connector.available)
  const connected = available.filter((connector) => connector.connected)
  const capabilityCount = useMemo(
    () => new Set(connected.flatMap((connector) => connector.unlocks || [])).size,
    [connected],
  )
  const mapConnectors = MAP_ORDER
    .map((id) => connectors.find((connector) => connector.id === id))
    .filter((connector): connector is Connector => !!connector)

  function renderConnectorCard(connector: Connector, comingSoon = false) {
    return (
      <article className={`integr-card${comingSoon ? ' integr-card--soon' : ''}`} key={connector.id}>
        <div className="integr-top">
          <span className="integr-logo"><img src={logoSrc(connector.id)} alt="" /></span>
          <div>
            <h3>{connector.title}</h3>
            <span className={`status-chip ${connector.connected ? 'status-chip--success' : 'status-chip--neutral'}`}>
              {connector.connected && <span className="status-chip__dot" />}
              {comingSoon ? 'Coming soon' : connector.connected ? 'Connected' : 'Not connected'}
            </span>
          </div>
        </div>
        <p>{BLURB[connector.id] || 'Connect this service to give Cash more useful context.'}</p>
        <div className="integr-foot">
          <span className="integr-unlocks">
            {comingSoon
              ? 'In development'
              : connector.unlocks?.length
                ? `${connector.unlocks.length} capabilities`
                : 'More context'}
          </span>
          {comingSoon ? (
            <button type="button" className="btn btn-ghost btn-small" disabled>Connect</button>
          ) : connector.connected ? (
            <button
              type="button"
              className="btn btn-ghost btn-small"
              disabled={actionId === connector.id}
              onClick={() => setDialog({ mode: 'disconnect', connector })}
            >
              Disconnect
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary btn-small"
              disabled={!!actionId}
              onClick={() => connect(connector)}
            >
              {actionId === connector.id && <span className="spinner spinner--button" aria-hidden="true" />}
              {actionId === connector.id ? 'Connecting…' : 'Connect'}
            </button>
          )}
        </div>
      </article>
    )
  }

  return (
    <>
      <PageHeader
        title="About Cash"
        description="See the tools, context, and capabilities available to your assistant."
      />

      <div className="app-body library-body">
        <div className="library-tabs" role="tablist" aria-label="Cash workspace views">
          {([
            ['identity', 'Identity'],
            ['integrations', 'Integrations'],
            ['skills', 'Skills'],
          ] as const).map(([id, label]) => (
            <button
              type="button"
              role="tab"
              key={id}
              className={view === id ? 'active' : ''}
              aria-selected={view === id}
              onClick={() => setView(id)}
            >
              {label}
            </button>
          ))}
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

        {loading ? (
          <div className="library-loading" aria-label="Loading Cash workspace" aria-busy="true">
            <span className="skeleton library-loading__profile" />
            <span className="skeleton library-loading__map" />
          </div>
        ) : loadError ? (
          <div className="state-panel" role="alert">
            <span className="state-panel__icon"><RefreshIcon /></span>
            <h2>Cash’s workspace didn’t load</h2>
            <p>{loadError}</p>
            <button type="button" className="btn btn-primary" onClick={() => void load()}>
              <RefreshIcon /> Try again
            </button>
          </div>
        ) : view === 'identity' ? (
          <section className="assistant-overview" aria-label="Cash identity and integration map">
            <article className="assistant-profile-card">
              <div className="assistant-profile-card__heading">
                <h2>Cash</h2>
                <span className="status-chip status-chip--success"><span className="status-chip__dot" />Active</span>
              </div>
              <span className="assistant-profile-card__mark" aria-hidden="true"><CashMark /></span>
              <p className="assistant-profile-card__role">
                A steady, context-aware chief of staff that helps you plan, remember, follow up, and get work done.
              </p>
              <dl className="assistant-profile-stats">
                <div><dt>Connected tools</dt><dd>{connected.length}</dd></div>
                <div><dt>Capabilities</dt><dd>{capabilityCount}</dd></div>
                <div><dt>Memory</dt><dd>On</dd></div>
              </dl>
            </article>

            <div className="capability-map">
              <div className="capability-map__grid" aria-hidden="true" />
              <svg className="capability-map__lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                <line x1="50" y1="50" x2="50" y2="16" />
                <line x1="50" y1="50" x2="78" y2="32" />
                <line x1="50" y1="50" x2="78" y2="68" />
                <line x1="50" y1="50" x2="50" y2="84" />
                <line x1="50" y1="50" x2="22" y2="68" />
                <line x1="50" y1="50" x2="22" y2="32" />
              </svg>
              <span className="capability-map__center" aria-label="Cash">
                <CashMark />
              </span>
              {mapConnectors.map((connector, index) => (
                <button
                  type="button"
                  key={connector.id}
                  className={`map-node map-node--${index + 1}${connector.connected ? ' is-connected' : ''}`}
                  onClick={() => connector.available && !connector.connected && connect(connector)}
                  disabled={!connector.available || connector.connected}
                  title={connector.connected ? `${connector.title} is connected` : `Connect ${connector.title}`}
                >
                  <img src={logoSrc(connector.id)} alt="" />
                  <span>{connector.title}</span>
                </button>
              ))}
              <div className="capability-map__legend">
                <span><i className="legend-dot legend-dot--connected" />Connected</span>
                <span><i className="legend-dot" />Available</span>
              </div>
            </div>
          </section>
        ) : view === 'integrations' ? (
          <>
            <section aria-labelledby="available-integrations-title">
              <h2 className="subhead" id="available-integrations-title">Available</h2>
              <div className="integr-grid">{available.map((connector) => renderConnectorCard(connector))}</div>
            </section>
            {soon.length > 0 && (
              <section className="coming-soon" aria-labelledby="coming-soon-title">
                <h2 className="subhead" id="coming-soon-title">Coming soon</h2>
                <div className="integr-grid">{soon.map((connector) => renderConnectorCard(connector, true))}</div>
              </section>
            )}
          </>
        ) : (
          <section className="skills-panel">
            <span className="skills-panel__icon"><SparklesIcon /></span>
            <div>
              <p className="eyebrow">Unlocked by your connections</p>
              <h2>{capabilityCount || 0} active capabilities</h2>
              <p>Every connected tool gives Cash more context and more ways to help.</p>
            </div>
            <div className="skill-list">
              {connected.flatMap((connector) => connector.unlocks || []).map((skill) => (
                <span key={skill}>{skill.replaceAll('.', ' ')}</span>
              ))}
              {capabilityCount === 0 && <span>Connect a tool to unlock your first capability.</span>}
            </div>
          </section>
        )}
      </div>

      <ConfirmDialog
        open={!!dialog}
        title={dialog?.mode === 'disconnect' ? `Disconnect ${dialog.connector.title}?` : `Connect ${dialog?.connector.title || 'service'}`}
        description={
          dialog?.mode === 'disconnect'
            ? `Cash will stop using ${dialog.connector.title} until you connect it again.`
            : dialog?.connector.connect_hint || 'Follow the setup steps Cash gives you in chat.'
        }
        confirmLabel={dialog?.mode === 'disconnect' ? 'Disconnect' : 'Got it'}
        tone={dialog?.mode === 'disconnect' ? 'danger' : 'primary'}
        hideCancel={dialog?.mode === 'hint'}
        busy={!!dialog && actionId === dialog.connector.id}
        onClose={() => setDialog(null)}
        onConfirm={() => void confirmDialog()}
      />
    </>
  )
}
