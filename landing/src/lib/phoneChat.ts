// The looping iMessage-style chat shown inside the phone mockup. Shared by the
// hero scene (desktop) and the static mobile phone in the sequence section.
export interface ChatStep {
  t: 'me' | 'cash' | 'typing' | 'act'
  x?: string
  src?: string
  tt?: string
  ss?: string
}

export const CHAT: ChatStep[] = [
  { t: 'me', x: 'Reschedule my afternoon sync' },
  { t: 'typing' },
  { t: 'cash', x: 'Done. Moved it to 4:15 and looped in the team.' },
  { t: 'act', src: '/assets/logos/google-calendar.png', tt: 'Rescheduled meeting', ss: 'Now 4:15 PM · invites updated' },
  { t: 'act', src: '/assets/logos/slack.svg', tt: 'Replied in Slack', ss: '#team · "moved to 4:15, thanks!"' },
  { t: 'me', x: 'How are my markets looking?' },
  { t: 'typing' },
  { t: 'act', src: '/assets/logos/coinbase.png', tt: 'Crypto portfolio summarized', ss: '+2.4% today · BTC, ETH, SOL' },
  { t: 'act', src: '/assets/logos/tradingview.svg', tt: 'Market alert created', ss: 'Ping me if BTC drops 3%' },
  { t: 'act', src: '/assets/logos/gmail.svg', tt: 'Email draft prepared', ss: 'Reply to Suhail · ready to review' },
]

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

/** Run the looping chat inside the given `.hp-chat` element. */
export function runChatOn(hpChat: HTMLElement) {
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
