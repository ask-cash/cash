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
  '<svg viewBox="0 0 64 64"><g fill="#0a0a0c"><polygon points="18,19 21,3 32,16"/><polygon points="46,19 43,3 32,16"/><circle cx="32" cy="27" r="13"/><path d="M21,35 C16,46 15,55 21,59 L43,59 C49,55 48,46 43,35 Z"/><path d="M43,58 C57,57 60,43 51,38 C57,45 50,53 42,51 Z"/></g></svg>'

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
