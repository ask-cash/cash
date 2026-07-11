import { useEffect, useState } from 'react'
import { fetchConnectors, disconnectConnector, type Connector } from '../../lib/api'
import { logoSrc } from '../../data/logos'

// Short blurbs per provider id (the API doesn't carry marketing copy).
const BLURB: Record<string, string> = {
  google_calendar: 'See and manage your schedule, resolve conflicts, get a morning brief.',
  gmail: 'Triage and summarise your inbox.',
  outlook: 'Your Outlook calendar, unified with the rest.',
  discord: 'Bring Cash into your Discord DMs — one memory across platforms.',
  telegram: 'Chat with Cash from Telegram — same brain, same memory.',
  slack: 'Cash in your workspace channels and DMs.',
  notion: 'Read and write your workspace docs.',
  hubspot: 'CRM context, watched for you.',
  linear: 'Track issues and ship updates.',
  twitter: 'Your timeline, summarised.',
}

export default function Integrations() {
  const [connectors, setConnectors] = useState<Connector[]>([])
  const [loading, setLoading] = useState(true)

  async function load() {
    setConnectors(await fetchConnectors())
    setLoading(false)
  }
  useEffect(() => { load() }, [])

  // Surface an OAuth result banner (?connected= / ?error= from the callback).
  const params = new URLSearchParams(window.location.search)
  const justConnected = params.get('connected')
  const oauthError = params.get('error')

  function connect(c: Connector) {
    if (c.id === 'google_calendar') {
      window.location.href = '/api/connect/google/start'
      return
    }
    // Account-link providers (Telegram/Discord) connect from their app; show how.
    alert(c.connect_hint || 'Follow the steps Cash gives you in chat to connect.')
  }

  async function disconnect(c: Connector) {
    await disconnectConnector(c.id)
    load()
  }

  const available = connectors.filter((c) => c.available)
  const soon = connectors.filter((c) => !c.available)

  return (
    <>
      <div className="app-head"><h1>Integrations</h1></div>
      <div className="app-body">
        {justConnected && (
          <div className="auth-err" style={{ background: 'rgba(10,10,12,.05)' }}>
            ✅ Connected {justConnected.replace('-', ' ')} — you're all set.
          </div>
        )}
        {oauthError && <div className="auth-err">Couldn't finish connecting. Please try again.</div>}
        <p className="section-note">Connect the tools you live in. Each connection unlocks more of what Cash can do.</p>

        {loading ? (
          <p className="section-note">Loading…</p>
        ) : (
          <>
            <div className="integr-grid">
              {available.map((c) => (
                <div className="integr-card" key={c.id}>
                  <div className="integr-top">
                    <span className="integr-logo"><img src={logoSrc(c.id)} alt={c.title} /></span>
                    <h3>{c.title}</h3>
                  </div>
                  <p>{BLURB[c.id] || ''}</p>
                  <div className="integr-foot">
                    <span className={'tag ' + (c.connected ? 'on' : 'off')}>
                      {c.connected ? 'Connected' : 'Not connected'}
                    </span>
                    {c.connected ? (
                      <button className="btn btn-ghost" onClick={() => disconnect(c)}>Disconnect</button>
                    ) : (
                      <button className="btn btn-primary" onClick={() => connect(c)}>Connect</button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {soon.length > 0 && <div className="subhead">Coming soon</div>}
            <div className="integr-grid">
              {soon.map((c) => (
                <div className="integr-card soon" key={c.id}>
                  <div className="integr-top">
                    <span className="integr-logo"><img src={logoSrc(c.id)} alt={c.title} /></span>
                    <h3>{c.title}</h3>
                  </div>
                  <p>{BLURB[c.id] || ''}</p>
                  <div className="integr-foot">
                    <span className="tag soon">Coming soon</span>
                    <button className="btn btn-ghost" disabled>Connect</button>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </>
  )
}
