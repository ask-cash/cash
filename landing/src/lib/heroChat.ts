// Hero conversation: a bare Telegram-style thread that types itself out on a
// loop. It seeds with the first exchange already visible so the hero is never
// empty, then starts animating once it scrolls into view.
const SCRIPT: { who: 'me' | 'bot'; t: string }[] = [
  { who: 'me', t: 'Hi, Cash. What can you do?' },
  { who: 'bot', t: 'I read your Slack, move your meetings, draft your replies and watch your markets.' },
  { who: 'me', t: 'All of it from here?' },
  { who: 'bot', t: 'All of it from here. Just message me.' },
]

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

export function initHeroChat() {
  const body = document.getElementById('heroChatBody')
  if (!body) return
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  const el = (cls: string, html?: string) => {
    const d = document.createElement('div')
    d.className = cls
    if (html) d.innerHTML = html
    return d
  }
  // keep the visible stack short so the thread never overflows the hero
  const trim = () => {
    while (body.children.length > 5) body.removeChild(body.firstChild!)
  }

  function seed() {
    body!.innerHTML = ''
    SCRIPT.slice(0, 2).forEach((m) => {
      const b = el('hc-msg ' + m.who)
      b.textContent = m.t
      b.classList.add('show')
      body!.appendChild(b)
    })
  }

  async function run(): Promise<void> {
    body!.innerHTML = ''
    if (reduce) {
      SCRIPT.forEach((m) => {
        const b = el('hc-msg ' + m.who)
        b.textContent = m.t
        b.classList.add('show')
        body!.appendChild(b)
      })
      return
    }
    for (const m of SCRIPT) {
      if (m.who === 'bot') {
        const t = el('hc-typing', '<i></i><i></i><i></i>')
        body!.appendChild(t)
        trim()
        await wait(60)
        t.classList.add('show')
        await wait(900 + Math.min(900, m.t.length * 14))
        t.remove()
      } else {
        await wait(520)
      }
      const b = el('hc-msg ' + m.who)
      b.textContent = m.t
      body!.appendChild(b)
      trim()
      await wait(50)
      b.classList.add('show')
      await wait(m.who === 'bot' ? 1150 : 420)
    }
    await wait(3400)
    return run()
  }

  seed()
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          io.disconnect()
          setTimeout(run, 2200)
        }
      })
    },
    { threshold: 0.2 },
  )
  io.observe(body)
}
