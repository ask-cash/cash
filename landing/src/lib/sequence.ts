// "Watch it work" — the pinned Telegram thread. Scroll progress through the
// 300vh section drives how many messages have landed; the thread scrolls itself
// so the newest bubble stays at the bottom edge, and the step rail highlights
// whichever action Cash just took.
import { logoSrc } from '../data/integrations'

interface Msg {
  who: 'u' | 'c'
  text: string
  time: string
  app?: string
  label?: string
  kb?: string[]
}

const CONVO: Msg[] = [
  { who: 'u', text: 'What did I miss in Slack?', time: '9:41' },
  {
    who: 'c',
    text: '3 new threads in #launch. Priya needs the copy deck by 5pm and the design review moved to Thursday.',
    app: 'Slack',
    label: 'Slack',
    time: '9:41',
  },
  { who: 'u', text: 'Move my 3pm sync to 4:15', time: '9:42' },
  {
    who: 'c',
    text: 'Done. Calendar updated and everyone has been notified.',
    app: 'Google Calendar',
    label: 'Google Calendar',
    time: '9:42',
  },
  { who: 'u', text: 'Tell the team in #launch', time: '9:43' },
  {
    who: 'c',
    text: 'Posted in #launch. Want me to block focus time before the call?',
    app: 'Slack',
    label: 'Slack',
    time: '9:43',
    kb: ['Yes, block it', 'Not now'],
  },
]

const STEPS = [
  { app: 'Slack', label: 'Catches you up on Slack' },
  { app: 'Google Calendar', label: 'Reschedules your meetings' },
  { app: 'Slack', label: 'Replies for you in channel' },
]

const TICK =
  '<svg class="tick" viewBox="0 0 18 11" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M1 6l3.2 3.2L10.6 2"/><path d="M7.4 9.2L13.8 2"/></svg>'

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))

export function initSequence() {
  const seq = document.getElementById('seq')
  const body = document.getElementById('seqBody')
  const stepsEl = document.getElementById('seqSteps')
  const cue = document.getElementById('seqCue')
  if (!seq || !body || !stepsEl || !cue) return

  let markup = '<div class="seq-day">Today</div>'
  CONVO.forEach((m, i) => {
    // every Cash reply is preceded by its own typing indicator
    if (m.who === 'c') markup += '<div class="cb-typing" data-t="' + i + '"><i></i><i></i><i></i></div>'
    const tag = m.app
      ? '<span class="tag"><img src="' + logoSrc(m.app) + '" alt="">via ' + m.label + '</span>'
      : ''
    const kb = m.kb ? '<span class="kb">' + m.kb.map((k) => '<span>' + k + '</span>').join('') + '</span>' : ''
    const meta = '<span class="meta">' + m.time + (m.who === 'u' ? TICK : '') + '</span>'
    markup += '<div class="cb ' + m.who + '" data-i="' + i + '">' + m.text + tag + kb + meta + '</div>'
  })
  markup += '<div class="seq-delivered" id="seqDelivered">Delivered</div>'
  body.innerHTML = '<div class="seq-track" id="seqTrack">' + markup + '</div>'

  const track = document.getElementById('seqTrack')
  const bubbles = [...body.querySelectorAll<HTMLElement>('.cb')]
  const typers = [...body.querySelectorAll<HTMLElement>('.cb-typing')]
  const delivered = document.getElementById('seqDelivered')!

  stepsEl.innerHTML = STEPS.map(
    (s, i) =>
      '<li class="seq-step" data-i="' + i + '"><span class="si"><img src="' + logoSrc(s.app) +
      '" alt=""></span><span class="st">' + s.label + '</span></li>',
  ).join('')
  const steps = [...stepsEl.querySelectorAll<HTMLElement>('.seq-step')]

  // How far through the thread we are, and whether the next reply is "typing".
  // Scroll drives this when the stage is pinned; a timer drives it on phones.
  function paint(n: number, frac: number, cueOpacity: string) {
    bubbles.forEach((b, i) => b.classList.toggle('show', i < n))
    // show the typing bubble once we're partway toward the next Cash reply
    typers.forEach((t) => t.classList.toggle('show', +t.dataset.t! === n && frac > 0.25))

    if (track) {
      const last = bubbles[n - 1]
      if (last) {
        const need = last.offsetTop + last.offsetHeight + 10 - body!.clientHeight
        track.style.transform = 'translateY(' + (need > 0 ? -Math.round(need) : 0) + 'px)'
      } else {
        track.style.transform = 'translateY(0px)'
      }
    }

    const lastShown = CONVO[n - 1]
    delivered.classList.toggle('show', n > 0 && !!lastShown && lastShown.who === 'u')
    const shownCash = CONVO.slice(0, n).filter((m) => m.who === 'c').length
    const active = clamp(shownCash - 1, 0, STEPS.length - 1)
    steps.forEach((s, i) => s.classList.toggle('on', n > 0 && i === active))
    cue!.style.opacity = cueOpacity
  }

  // --- pinned (desktop): scroll position through the 300vh runway ------------
  function update() {
    const rect = seq!.getBoundingClientRect()
    const total = seq!.offsetHeight - window.innerHeight
    const p = total > 0 ? clamp(-rect.top / total, 0, 1) : 0
    // the thread plays out over the middle 80% of the pin, leaving a lead-in
    const f = clamp((p - 0.04) / 0.8, 0, 1) * (bubbles.length - 1)
    const n = Math.min(bubbles.length, Math.floor(f) + 1)
    paint(n, f - n, p > 0.04 && p < 0.9 ? '0.6' : '0')
  }

  // --- unpinned (phones): play once the phone is actually on screen ----------
  const unpinned = window.matchMedia('(max-width:900px)')
  const reduced = window.matchMedia('(prefers-reduced-motion:reduce)')
  let timer = 0
  let played = false

  function stopTimer() {
    if (timer) window.clearTimeout(timer)
    timer = 0
  }

  function play(n = 0) {
    if (n > bubbles.length) return
    paint(n, 0, '0')
    if (n === bubbles.length) return
    // pause on the typing indicator before each of Cash's replies
    const next = CONVO[n]
    const typing = next && next.who === 'c'
    if (typing) paint(n, 0.5, '0')
    timer = window.setTimeout(() => play(n + 1), typing ? 1500 : 900)
  }

  const observer = new IntersectionObserver(
    (entries) => {
      if (!unpinned.matches || played) return
      if (entries.some((e) => e.isIntersecting)) {
        played = true
        observer.disconnect()
        if (reduced.matches) paint(bubbles.length, 0, '0')
        else timer = window.setTimeout(() => play(1), 400)
      }
    },
    // The phone is ~610px tall, so a high threshold never fires on a short
    // screen — start as soon as a decent slice of it is up.
    { threshold: 0.12 },
  )

  let raf = 0
  const onScroll = () => {
    if (unpinned.matches) return
    if (raf) cancelAnimationFrame(raf)
    raf = requestAnimationFrame(update)
  }

  function applyMode() {
    stopTimer()
    if (unpinned.matches) {
      // Reset and wait for the phone to scroll into view.
      played = false
      paint(0, 0, '0')
      const phone = seq!.querySelector('.seq-phone')
      if (phone) observer.observe(phone)
    } else {
      observer.disconnect()
      update()
    }
  }

  applyMode()
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', () => {
    if (!unpinned.matches) update()
  })
  unpinned.addEventListener('change', applyMode)
}
