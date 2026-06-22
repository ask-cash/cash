// Scroll-driven app sequence. As #seq scrolls, a card cycles through each app
// action, then a finale clones the live hero scene so the logos emerge from the
// exact scattered positions.
import { logoSrc } from '../data/integrations'

interface Step {
  key?: string
  app?: string
  t?: string
  s?: string
  imessage?: boolean
  bubbles?: string[]
}

const IMSG_ICON =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 120'%3E%3Cdefs%3E%3ClinearGradient id='m' x1='0' y1='0' x2='0' y2='1'%3E%3Cstop offset='0' stop-color='%235BF675'/%3E%3Cstop offset='1' stop-color='%231FAD2B'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='120' height='120' rx='27' fill='url(%23m)'/%3E%3Cpath d='M60 26C39 26 22 39.5 22 56.5c0 9.6 5.4 18.1 13.8 23.6-1 4.6-3.9 9-7.6 12.2 6.4-.6 12.7-2.7 18-6.4 4.2 1.2 8.8 1.9 13.8 1.9 21 0 38-13.5 38-30.5S81 26 60 26z' fill='%23fff'/%3E%3C/svg%3E"

const STEPS: Step[] = [
  { key: 'Slack', app: 'Slack', t: 'Replied in #team', s: '“Moved to 4:15 — works for everyone?” Sent in your voice.' },
  { key: 'Google Calendar', app: 'Calendar', t: 'Meeting rescheduled', s: 'Afternoon sync → 4:15 PM. Every invite updated automatically.' },
  { key: 'Coinbase', app: 'Coinbase', t: 'Portfolio summarized', s: '+2.4% today across BTC, ETH and SOL — with a morning brief.' },
  { key: 'TradingView', app: 'TradingView', t: 'Market alert created', s: '“Ping me if BTC drops 3%.” Watching it for you, around the clock.' },
  { key: 'Gmail', app: 'Gmail', t: 'Email draft prepared', s: 'Reply to Priya drafted and waiting for your one-tap approval.' },
  { imessage: true, bubbles: ['Done — pushed it to 4:15 ✅', 'Anything else before your 5pm?'] },
]

export function initSequence() {
  const seq = document.getElementById('seq')
  if (!seq) return
  const card = document.getElementById('seqCard')!
  const logo = document.getElementById('seqLogo')!
  const logoImg = document.getElementById('seqLogoImg') as HTMLImageElement
  const msg = document.getElementById('seqMsg')!
  const appEl = document.getElementById('seqApp')!
  const titleEl = document.getElementById('seqTitle')!
  const subEl = document.getElementById('seqSub')!
  const bubbles = document.getElementById('seqBubbles')!
  const finale = document.getElementById('seqFinale')!
  const cue = document.getElementById('seqCue')!
  const scatter = document.getElementById('seqScatter')!
  const heroScene = document.getElementById('heroScene')
  const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))
  const SEGS = STEPS.length + 1

  let scatterClone: HTMLElement | null = null
  function buildScatter() {
    if (!scatter || !heroScene) return
    scatter.innerHTML = ''
    const clone = heroScene.cloneNode(true) as HTMLElement
    clone.removeAttribute('id')
    clone.classList.remove('in')
    clone.style.margin = '0'
    clone.style.width = (heroScene.clientWidth || window.innerWidth) + 'px'
    const ph = clone.querySelector<HTMLElement>('.hero-phone')
    if (ph) ph.style.visibility = 'hidden'
    const tl = clone.querySelector('.toast-layer')
    if (tl) tl.innerHTML = ''
    const ln = clone.querySelector<HTMLElement>('.scene-lines')
    if (ln) ln.style.display = 'none'
    const gl = clone.querySelector<HTMLElement>('.scene-glow')
    if (gl) gl.style.display = 'none'
    scatter.appendChild(clone)
    void clone.offsetWidth
    clone.classList.add('in')
    scatterClone = clone
  }
  function renderScatter(show: number, fade: number) {
    scatter.style.opacity = (clamp(show, 0, 1) * (1 - fade)).toFixed(3)
  }

  function setStep(step: Step) {
    const isMsg = !step.imessage
    msg.style.display = isMsg ? '' : 'none'
    bubbles.style.display = isMsg ? 'none' : 'flex'
    logo.style.display = ''
    if (isMsg) {
      logoImg.src = logoSrc(step.key!)
      appEl.textContent = step.app ?? ''
      titleEl.textContent = step.t ?? ''
      subEl.textContent = step.s ?? ''
    } else {
      logoImg.src = IMSG_ICON
      bubbles.innerHTML = (step.bubbles ?? []).map((b) => '<div class="bubble">' + b + '</div>').join('')
    }
  }
  function renderApp(_step: Step, t: number) {
    const inP = clamp(t / 0.25, 0, 1)
    const outP = clamp((t - 0.72) / 0.28, 0, 1)
    card.style.opacity = (inP * (1 - outP)).toFixed(3)
    card.style.transform = 'translateY(' + ((1 - inP) * 24 - outP * 24).toFixed(1) + 'px)'
    logo.style.transform = 'scale(' + (0.8 + 0.2 * inP).toFixed(3) + ')'
  }

  let finaleOn = false
  let heroClone: HTMLElement | null = null
  function enterFinale() {
    finale.style.opacity = '1'
    card.style.display = 'none'
    if (finaleOn) return
    finaleOn = true
    if (heroClone) heroClone.remove()
    if (!heroScene) return
    heroClone = heroScene.cloneNode(true) as HTMLElement
    heroClone.classList.remove('in')
    heroClone.removeAttribute('id')
    heroClone.style.margin = '0'
    heroClone.style.width = (heroScene.clientWidth || window.innerWidth) + 'px'
    finale.innerHTML = ''
    finale.appendChild(heroClone)
    void heroClone.offsetWidth
    heroClone.classList.add('in')
    playFinaleChat(heroClone)
  }
  function playFinaleChat(clone: HTMLElement) {
    const chat = clone.querySelector('.hp-chat')
    if (!chat) return
    chat.innerHTML = ''
    const script = [
      { me: true, x: 'Reschedule my afternoon sync' },
      { typing: true },
      { me: false, x: 'Done. Moved it to 4:15 and looped in the team.' },
      { me: true, x: 'Perfect — thanks' },
      { typing: true },
      { me: false, x: 'Also drafted your reply to Priya. Want me to send it?' },
    ]
    let i = 0
    ;(function tick() {
      if (clone !== heroClone || !clone.isConnected) return
      const m = script[i]
      const ty = chat.querySelector('.ctyping')
      if (ty) ty.remove()
      if (m.typing) {
        const t = document.createElement('div')
        t.className = 'ctyping'
        t.innerHTML =
          '<span style="width:6px;height:6px;border-radius:50%;background:#8a8a8e;display:inline-block"></span><span style="width:6px;height:6px;border-radius:50%;background:#8a8a8e;display:inline-block"></span><span style="width:6px;height:6px;border-radius:50%;background:#8a8a8e;display:inline-block"></span>'
        chat.appendChild(t)
      } else {
        const b = document.createElement('div')
        b.className = 'cmsg ' + (m.me ? 'me' : 'cash')
        b.textContent = m.x ?? ''
        chat.appendChild(b)
      }
      i++
      if (i < script.length) setTimeout(tick, m.typing ? 1100 : 850)
    })()
  }
  function exitFinale() {
    if (!finaleOn) return
    finaleOn = false
    finale.style.opacity = '0'
    card.style.display = ''
    if (heroClone) heroClone.classList.remove('in')
  }

  let lastIdx = -1
  function update() {
    const rect = seq!.getBoundingClientRect()
    const total = seq!.offsetHeight - window.innerHeight
    const p = clamp(-rect.top / total, 0, 1)
    const fpos = p * SEGS
    const idx = Math.min(Math.floor(fpos), SEGS - 1)
    const t = fpos - idx
    cue.style.opacity = p > 0.02 && p < 0.92 ? '0.5' : '0'
    let scFade = 0
    if (idx >= STEPS.length) scFade = 1
    else if (idx === STEPS.length - 1) scFade = clamp((t - 0.5) / 0.4, 0, 1)
    renderScatter(clamp(p / 0.05, 0, 1), scFade)
    if (idx < STEPS.length) {
      exitFinale()
      if (idx !== lastIdx) {
        setStep(STEPS[idx])
        lastIdx = idx
      }
      renderApp(STEPS[idx], t)
    } else {
      lastIdx = -1
      enterFinale()
    }
  }

  let raf = 0
  function onScroll() {
    if (raf) cancelAnimationFrame(raf)
    raf = requestAnimationFrame(update)
    update()
  }

  seq.style.height = SEGS * 88 + 'vh'
  buildScatter()
  update()
  // Reference scatterClone so the variable's purpose (current clone) is clear.
  void scatterClone
  window.addEventListener('scroll', onScroll, { passive: true })
  let rz: ReturnType<typeof setTimeout>
  window.addEventListener('resize', () => {
    clearTimeout(rz)
    rz = setTimeout(() => {
      buildScatter()
      update()
    }, 200)
  })
}
