// Integrations as a flat bracket grid — plain names, no marquee, no logo cards.
// [+] live today · [ ] on the way. Tracks services/integrations/registry.py.
interface Integ {
  name: string
  soon?: boolean
}
const INTEGRATIONS: Integ[] = [
  { name: 'Telegram' },
  { name: 'Discord' },
  { name: 'Google Calendar' },
  { name: 'Gmail' },
  { name: 'Google Drive' },
  { name: 'Outlook' },
  { name: 'Slack', soon: true },
  { name: 'Microsoft Teams', soon: true },
  { name: 'Notion', soon: true },
  { name: 'HubSpot', soon: true },
  { name: 'Linear', soon: true },
  { name: 'WhatsApp', soon: true },
]

export default function Integrations() {
  return (
    <section className="section" id="integrations">
      <div className="wrap">
        <div className="sec-label">
          <span className="br">## </span>plugs into what you already run on
        </div>
        <div className="integ-grid">
          {INTEGRATIONS.map((it) => (
            <div className="integ-item reveal" key={it.name}>
              <span className="mk">{it.soon ? '[ ]' : '[+]'}</span>
              <span className="nm">{it.name}</span>
              {it.soon && <span className="soon">soon</span>}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
