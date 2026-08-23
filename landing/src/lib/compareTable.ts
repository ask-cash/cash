// Builds the comparison grid inside #ctable.
const Y =
  '<span class="cmark"><span class="ic yes"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2"><polyline points="20 6 9 17 4 12"/></svg></span>'
const N =
  '<span class="cmark"><span class="ic no"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg></span>'
const E = '</span>'
const txt = (s: string) => '<span>' + s + '</span>'
const yes = (s: string) => Y + '<span>' + s + '</span>' + E
const no = (s: string) => N + '<span>' + s + '</span>' + E

const CASH_MARK =
  '<svg viewBox="0 0 64 64"><g fill="#0a0a0c"><path d="M17.5 7.5C19.5 13.5 21.5 17 24.5 19.2C26.8 18.2 29.3 17.7 32 17.7C34.7 17.7 37.2 18.2 39.5 19.2C42.5 17 44.5 13.5 46.5 7.5C48.6 14.6 49 21 47.6 26.4C49.6 31.5 50 36.5 49 41.5C48 47.5 46.5 53 44.5 57.5C40 59 24 59 19.5 57.5C17.5 53 16 47.5 15 41.5C14 36.5 14.4 31.5 16.4 26.4C15 21 15.4 14.6 17.5 7.5Z"/><path d="M44.8 56.8C52.2 56.6 57.6 51.4 57.6 45C57.6 40.4 54.9 36.7 51.1 35.5C53.7 38.3 54.9 41.7 54.5 45C53.9 50.1 49.9 53.7 44.9 54.1Z"/></g></svg>'

const cols = [
  { n: 'Cash', ic: CASH_MARK, cls: 'feat' },
  { n: 'Hermes', ic: '<img src="/assets/logos/hermes.svg" alt="Hermes">', cls: 'tile' },
  { n: 'OpenClaw', ic: '<img src="/assets/logos/openclaw.svg" alt="OpenClaw">', cls: 'tile' },
  { n: 'Claude Code', ic: '<img src="/assets/logos/claude-code.svg" alt="Claude Code">', cls: 'tile' },
]

const rows = [
  { l: 'License', v: [txt('MIT'), txt('MIT'), txt('Apache 2.0'), no('Proprietary')] },
  { l: 'Time to set up', v: [txt('Easy'), txt('Moderate'), txt('Difficult'), txt('Easy')] },
  {
    l: 'Native channels',
    v: [txt('iOS, macOS, Web, Voice, Email, Telegram, Slack, CLI'), txt('CLI / TUI'), txt('CLI, macOS, Web'), txt('CLI, macOS, Windows, Web')],
  },
  { l: 'Memory', v: [yes('Managed memory'), no('You build the memory stack'), no('Basic memory, context loss'), no('Limited')] },
  { l: 'Security', v: [yes('Built-in sandboxing'), no('DIY'), no('DIY'), no('No sandboxing')] },
  { l: 'Hosting', v: [yes('Cloud or self-hosted'), no('Self-hosted only'), no('Self-hosted only'), yes('Vendor cloud')] },
  { l: 'Native integrations', v: [yes('Managed OAuth connections'), no('No managed connectors'), no('No managed connectors'), no('MCP only')] },
  { l: 'Schedules', v: [yes('Cron + Heartbeat'), yes('Cron + Heartbeat'), yes('Cron + Heartbeat'), no('Cron only')] },
  { l: 'Pricing', v: [txt('Free + API costs, paid plans'), txt('Free + DIY hosting + API'), txt('Free + DIY hosting + API'), txt('Paid plans + API costs')] },
]

export function initCompareTable() {
  const t = document.getElementById('ctable')
  if (!t) return
  let html = '<div class="crow crow-head"><div></div>'
  cols.forEach((c) => {
    const inner = '<span class="ci">' + c.ic + '</span>'
    html += '<div class="' + (c.cls === 'feat' ? 'feat' : '') + '"><span class="co">' + inner + c.n + '</span></div>'
  })
  html += '</div>'
  rows.forEach((r) => {
    html += '<div class="crow"><div class="rlabel">' + r.l + '</div>'
    r.v.forEach((cell, i) => {
      html += '<div class="' + (i === 0 ? 'feat' : '') + '">' + cell + '</div>'
    })
    html += '</div>'
  })
  t.innerHTML = html
}
