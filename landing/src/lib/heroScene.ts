// Hero scene: scattered integration logos that emerge from the phone, a looping
// iMessage-style chat, pointer parallax, and edge action toasts.
import { INTEGR } from '../data/integrations'

interface ChatStep {
  t: 'me' | 'cash' | 'typing' | 'act'
  x?: string
  src?: string
  tt?: string
  ss?: string
}

const CHAT: ChatStep[] = [
  { t: 'me', x: 'Reschedule my afternoon sync' },
  { t: 'typing' },
  { t: 'cash', x: 'Done. Moved it to 4:15 and looped in the team.' },
  { t: 'act', src: '/assets/logos/google-calendar.png', tt: 'Rescheduled meeting', ss: 'Now 4:15 PM · invites updated' },
  { t: 'act', src: '/assets/logos/slack.svg', tt: 'Replied in Slack', ss: '#team · "moved to 4:15, thanks!"' },
  { t: 'me', x: 'How are my markets looking?' },
  { t: 'typing' },
  { t: 'act', src: '/assets/logos/coinbase.png', tt: 'Crypto portfolio summarized', ss: '+2.4% today · BTC, ETH, SOL' },
  { t: 'act', src: '/assets/logos/tradingview.svg', tt: 'Market alert created', ss: 'Ping me if BTC drops 3%' },
  { t: 'act', src: '/assets/logos/gmail.svg', tt: 'Email draft prepared', ss: 'Reply to Priya · ready to review' },
]

const TOASTS = [
  { src: '/assets/logos/google-calendar.png' },
  { src: '/assets/logos/slack.svg' },
  { src: '/assets/logos/coinbase.png' },
  { src: '/assets/logos/tradingview.svg' },
  { src: '/assets/logos/gmail.svg' },
]
const TOAST_META = [
  { app: 'Calendar', title: 'Meeting rescheduled', msg: 'Moved to 4:15 PM · invites updated' },
  { app: 'Slack', title: 'Replied in #team', msg: '“moved to 4:15, thanks!”' },
  { app: 'Coinbase', title: 'Portfolio summarized', msg: '+2.4% today · BTC, ETH, SOL' },
  { app: 'TradingView', title: 'Market alert created', msg: 'Ping me if BTC drops 3%' },
  { app: 'Gmail', title: 'Draft prepared', msg: 'Reply to Priya · ready to review' },
]
const ANCHORS = [
  { fx: 0.16, fy: 0.23 },
  { fx: 0.85, fy: 0.3 },
  { fx: 0.15, fy: 0.6 },
  { fx: 0.86, fy: 0.67 },
  { fx: 0.17, fy: 0.85 },
]

export function initHeroScene() {
  const heroScene = document.getElementById('heroScene')
  const orbitField = document.getElementById('orbitField')
  const sceneLines = document.getElementById('sceneLines') as unknown as SVGSVGElement | null
  const toastLayer = document.getElementById('toastLayer')
  const hpChat = document.getElementById('hpChat')

  function buildScene() {
    if (!heroScene || !orbitField || !sceneLines) return
    orbitField.innerHTML = ''
    while (sceneLines.firstChild) sceneLines.removeChild(sceneLines.firstChild)
    const w = heroScene.clientWidth
    const h = heroScene.clientHeight
    const cx = w / 2
    const cy = h / 2
    sceneLines.setAttribute('viewBox', `0 0 ${w} ${h}`)
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs')
    defs.innerHTML =
      '<linearGradient id="sg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2e86ab"/><stop offset="1" stop-color="#5bb8ed"/></linearGradient>'
    sceneLines.appendChild(defs)

    const SPOTS: [number, number][] = [
      [0.08, 0.09], [0.07, 0.31], [0.1, 0.53], [0.07, 0.76], [0.15, 0.93], [0.22, 0.19], [0.17, 0.43], [0.25, 0.66],
      [0.92, 0.11], [0.93, 0.35], [0.9, 0.58], [0.93, 0.83], [0.79, 0.21], [0.85, 0.46], [0.77, 0.71],
    ]
    INTEGR.forEach((it, i) => {
      const spot = SPOTS[i % SPOTS.length]
      const x = spot[0] * w
      const y = spot[1] * h
      const el = document.createElement('div')
      el.className = 'icard'
      el.style.left = x + 'px'
      el.style.top = y + 'px'
      el.style.setProperty('--dx', (cx - x).toFixed(1) + 'px')
      el.style.setProperty('--dy', (cy - y).toFixed(1) + 'px')
      const tier = [1.12, 1.0, 1.16, 1.04, 1.08][i % 5]
      el.style.setProperty('--s', tier.toFixed(2))
      el.style.setProperty('--bl', '0px')
      el.style.zIndex = String(Math.round(tier * 10))
      el.dataset.depth = (1.5 - tier).toFixed(2)
      el.style.transitionDelay = 0.05 * i + 0.04 + 's'
      const bob = document.createElement('div')
      bob.className = 'bob'
      bob.style.animationDelay = i * 0.35 + 's'
      bob.style.animationDuration = 5.5 + (i % 3) * 0.7 + 's'
      bob.innerHTML = `<img src="${it.src}" alt="${it.n}" />`
      el.appendChild(bob)
      el.title = it.n
      orbitField.appendChild(el)
    })
  }

  function buildHeroLogos() {
    const el = document.getElementById('heroLogos')
    if (!el) return
    el.innerHTML =
      INTEGR.slice(0, 10)
        .map(
          (it, i) =>
            '<div class="hl" style="animation-delay:' + i * 0.18 + 's"><img src="' + it.src + '" alt="' + it.n + '"></div>',
        )
        .join('') + '<span class="hlmore">&amp; more</span>'
  }

  // ---- phone chat loop ----
  function chatNode(step: ChatStep): HTMLElement {
    if (step.t === 'me' || step.t === 'cash') {
      const d = document.createElement('div')
      d.className = 'cmsg ' + (step.t === 'me' ? 'me' : 'cash')
      d.textContent = step.x ?? ''
      return d
    }
    if (step.t === 'typing') {
      const d = document.createElement('div')
      d.className = 'ctyping'
      d.innerHTML = '<i></i><i></i><i></i>'
      return d
    }
    const d = document.createElement('div')
    d.className = 'cact'
    d.innerHTML = `<span class="ci"><img src="${step.src}" alt="" /></span><span class="ct">${step.tt}<small>${step.ss}</small></span><span class="cok">✓</span>`
    return d
  }
  function runChat() {
    if (!hpChat) return
    let i = 0
    const tick = () => {
      const step = CHAT[i]
      while (hpChat.children.length > 4) hpChat.removeChild(hpChat.firstChild!)
      const node = chatNode(step)
      hpChat.appendChild(node)
      if (step.t === 'me') {
        const dv = document.createElement('div')
        dv.className = 'cdelivered'
        dv.innerHTML = 'Delivered'
        hpChat.appendChild(dv)
      }
      const wasTyping = step.t === 'typing'
      i = (i + 1) % CHAT.length
      if (i === 0) {
        setTimeout(() => {
          hpChat.innerHTML = ''
          tick()
        }, 2600)
        return
      }
      if (wasTyping) {
        setTimeout(() => {
          if (node.parentNode) node.remove()
          tick()
        }, 1100)
      } else {
        setTimeout(tick, step.t === 'me' ? 900 : 1300)
      }
    }
    tick()
  }

  // ---- action toasts ----
  let toastEls: (HTMLElement & { _i?: number })[] = []
  function placeToasts() {
    if (!toastLayer || !heroScene) return
    const W = heroScene.clientWidth
    const H = heroScene.clientHeight
    toastEls.forEach((t) => {
      const a = ANCHORS[t._i!]
      const half = t.offsetWidth / 2 + 6
      let x = a.fx * W
      x = Math.max(half, Math.min(W - half, x))
      t.style.left = x + 'px'
      t.style.top = a.fy * H + 'px'
    })
  }
  function buildToasts() {
    if (!toastLayer) return
    toastLayer.innerHTML = ''
    toastEls = TOASTS.map((to, i) => {
      const m = TOAST_META[i] || ({} as (typeof TOAST_META)[number])
      const el = document.createElement('div') as HTMLElement & { _i?: number }
      el.className = 'toast'
      el._i = i
      el.innerHTML =
        `<span class="nicon"><img src="${to.src}" alt="" /></span>` +
        `<div class="nbody"><div class="ntop"><span class="napp">${m.app || ''}</span><span class="ntime">now</span></div>` +
        `<div class="ntitle">${m.title || ''}</div><div class="nmsg">${m.msg || ''}</div></div>`
      toastLayer.appendChild(el)
      return el
    })
    placeToasts()
  }
  let toastIdx = 0
  function cycleToasts() {
    if (!toastEls.length) return
    const el = toastEls[toastIdx % toastEls.length]
    placeToasts()
    el.classList.add('show')
    setTimeout(() => el.classList.remove('show'), 3800)
    toastIdx++
    setTimeout(cycleToasts, 2200)
  }

  buildScene()
  buildHeroLogos()
  buildToasts()
  runChat()

  let st: ReturnType<typeof setTimeout>
  window.addEventListener('resize', () => {
    clearTimeout(st)
    st = setTimeout(() => {
      buildScene()
      placeToasts()
    }, 200)
  })

  if (heroScene) {
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(
        (es, ob) => {
          es.forEach((e) => {
            if (e.isIntersecting) {
              heroScene.classList.add('in')
              ob.disconnect()
            }
          })
        },
        { threshold: 0.15 },
      ).observe(heroScene)
    } else {
      heroScene.classList.add('in')
    }
    setTimeout(() => heroScene.classList.add('in'), 350)

    let pfRAF: number | null = null
    heroScene.addEventListener('pointermove', (e) => {
      if (pfRAF) return
      pfRAF = requestAnimationFrame(() => {
        pfRAF = null
        const r = heroScene.getBoundingClientRect()
        const nx = (e.clientX - r.left) / r.width - 0.5
        const ny = (e.clientY - r.top) / r.height - 0.5
        orbitField?.querySelectorAll<HTMLElement>('.icard').forEach((el) => {
          const d = parseFloat(el.dataset.depth || '0.6')
          el.style.setProperty('--px', (-nx * 26 * d).toFixed(1) + 'px')
          el.style.setProperty('--py', (-ny * 22 * d).toFixed(1) + 'px')
        })
      })
    })
    heroScene.addEventListener('pointerleave', () => {
      orbitField?.querySelectorAll<HTMLElement>('.icard').forEach((el) => {
        el.style.setProperty('--px', '0px')
        el.style.setProperty('--py', '0px')
      })
    })
  }

  setTimeout(cycleToasts, 900)
}
