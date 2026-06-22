// "Get access" waitlist flow: a Typeform-style modal that walks through the
// questions and submits the collected answers to Supabase.
import { QUESTIONS, type Question } from '../data/questions'
import { logoSrc } from '../data/integrations'
import { submitWaitlist, type WaitlistSignup } from './supabase'

type Answer = string | string[]

export function initWaitlist() {
  const overlay = document.getElementById('tfOverlay')
  if (!overlay) return
  const stage = document.getElementById('tfStage')!
  const bar = document.getElementById('tfBar')!
  const prevB = document.getElementById('tfPrev') as HTMLButtonElement
  const nextB = document.getElementById('tfNext') as HTMLButtonElement
  const emailOk = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)
  const LETTERS = 'ABCDEFGH'

  const QS = QUESTIONS
  const answers: Record<string, Answer> = {}
  let i = 0

  const str = (id: string) => (typeof answers[id] === 'string' ? (answers[id] as string) : '')
  const arr = (id: string) => (Array.isArray(answers[id]) ? (answers[id] as string[]) : [])

  function setProgress() {
    bar.style.width = (i / QS.length) * 100 + '%'
  }

  function render() {
    setProgress()
    prevB.disabled = i === 0
    const Q = QS[i]
    if (answers[Q.id] === undefined) answers[Q.id] = Q.type === 'multi' ? [] : ''
    let h = '<div class="tf-screen">'
    h += '<div class="tf-qnum">' + (i + 1) + ' &rarr; ' + QS.length + '</div>'
    h +=
      '<div class="tf-q">' +
      Q.q +
      (Q.type === 'email' || Q.type === 'single' || (Q.type === 'text' && !Q.optional) ? ' <span class="req">*</span>' : '') +
      '</div>'
    if (Q.sub) h += '<div class="tf-sub">' + Q.sub + '</div>'

    if (Q.type === 'single' || Q.type === 'multi') {
      h += '<div class="tf-opts" id="tfOpts">'
      ;(Q.options ?? []).forEach((o, idx) => {
        const sel = Q.type === 'multi' ? arr(Q.id).includes(o) : str(Q.id) === o
        const lg = Q.logos ? '<img class="tlogo" src="' + logoSrc(o) + '" alt="">' : ''
        h +=
          '<button type="button" class="tf-opt' +
          (sel ? ' sel' : '') +
          '" data-val="' +
          o +
          '">' +
          '<span class="k">' +
          (LETTERS[idx] || '') +
          '</span>' +
          lg +
          '<span class="lbl">' +
          o +
          '</span>' +
          '<svg class="ck" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></button>'
      })
      h += '</div>'
      if (Q.type === 'multi') {
        h +=
          '<div class="tf-actions"><button class="tf-ok" id="tfOk">OK <span class="arr">↵</span></button><span class="tf-keyhint">or press <b>Enter</b></span></div>'
      }
    } else {
      h +=
        '<div class="tf-input"><input type="' +
        (Q.type === 'email' ? 'email' : 'text') +
        '" id="tfField" placeholder="' +
        (Q.placeholder ?? '') +
        '" value="' +
        str(Q.id) +
        '" autocomplete="' +
        (Q.type === 'email' ? 'email' : Q.id === 'name' ? 'name' : 'off') +
        '"></div>'
      h +=
        '<div class="tf-err" id="tfErr"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg> <span></span></div>'
      h +=
        '<div class="tf-actions"><button class="tf-ok" id="tfOk">' +
        (i === QS.length - 1 ? 'Get access' : 'OK') +
        ' <span class="arr">↵</span></button><span class="tf-keyhint">press <b>Enter</b></span></div>'
    }
    h += '</div>'
    stage.innerHTML = h

    if (Q.type === 'single') {
      stage.querySelectorAll<HTMLElement>('.tf-opt').forEach((b) => {
        b.addEventListener('click', () => {
          answers[Q.id] = b.dataset.val!
          stage.querySelectorAll('.tf-opt').forEach((x) => x.classList.remove('sel'))
          b.classList.add('sel')
          setTimeout(advance, 240)
        })
      })
    } else if (Q.type === 'multi') {
      stage.querySelectorAll<HTMLElement>('.tf-opt').forEach((b) => {
        b.addEventListener('click', () => {
          const v = b.dataset.val!
          const a = arr(Q.id)
          const k = a.indexOf(v)
          if (k >= 0) {
            a.splice(k, 1)
            b.classList.remove('sel')
          } else {
            a.push(v)
            b.classList.add('sel')
          }
        })
      })
      stage.querySelector('#tfOk')!.addEventListener('click', advance)
    } else {
      const f = stage.querySelector('#tfField') as HTMLInputElement
      f.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          advance()
        }
      })
      stage.querySelector('#tfOk')!.addEventListener('click', advance)
      setTimeout(() => f.focus(), 60)
    }
  }

  function showErr(m: string) {
    const e = stage.querySelector('#tfErr')
    if (e) {
      e.querySelector('span')!.textContent = m
      e.classList.add('show')
    }
  }

  function advance() {
    const Q = QS[i]
    if (Q.type === 'single' && !str(Q.id)) return
    if (Q.type === 'multi' && arr(Q.id).length === 0) return
    if (Q.type === 'text' && !Q.optional) {
      const v = (stage.querySelector('#tfField') as HTMLInputElement).value.trim()
      answers[Q.id] = v
      if (!v) {
        showErr('This field is required.')
        return
      }
    }
    if (Q.type === 'text' && Q.optional) {
      answers[Q.id] = (stage.querySelector('#tfField') as HTMLInputElement).value.trim()
    }
    if (Q.type === 'email') {
      const v = (stage.querySelector('#tfField') as HTMLInputElement).value.trim()
      answers[Q.id] = v
      if (!emailOk(v)) {
        showErr('Please enter a valid email address.')
        return
      }
    }
    if (i < QS.length - 1) {
      i++
      render()
    } else {
      void submit()
    }
  }
  function back() {
    if (i > 0) {
      i--
      render()
    }
  }

  function buildPayload(): WaitlistSignup {
    return {
      email: str('email'),
      name: str('name') || null,
      role: str('role') || null,
      use_cases: arr('use'),
      tools: arr('tools'),
      priority: str('priority') || null,
    }
  }

  function renderSuccess() {
    const name = str('name')
    const email = str('email')
    stage.innerHTML =
      '<div class="tf-screen tf-success">' +
      '<div class="tf-check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><polyline points="20 6 9 17 4 12"/></svg></div>' +
      '<div class="big">You are on the list' +
      (name ? ', ' + name.split(' ')[0] : '') +
      '.</div>' +
      '<p>Cash will reach out at <b>' +
      (email || 'your inbox') +
      '</b> the moment your access opens. Talk soon.</p>' +
      '<div class="rr"><span style="width:7px;height:7px;border-radius:50%;background:var(--gold,#c9820f);display:inline-block"></span> Your place is reserved</div>' +
      '</div>'
  }

  async function submit() {
    bar.style.width = '100%'
    prevB.style.display = nextB.style.display = 'none'
    // brief "joining" state keeps the transition smooth while we write the row
    stage.innerHTML =
      '<div class="tf-screen tf-success"><div class="tf-check" style="background:transparent"><svg class="tf-spin" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2.4"><path d="M21 12a9 9 0 1 1-6.2-8.5"/></svg></div><div class="big" style="font-size:clamp(22px,4vw,32px)">Saving your spot…</div></div>'
    const err = await submitWaitlist(buildPayload())
    if (err) {
      // Don't block the user on a storage hiccup — log it and still confirm.
      console.error('[cash] could not store signup:', err)
    }
    renderSuccess()
  }

  function open() {
    overlay!.classList.add('open')
    document.body.style.overflow = 'hidden'
    i = 0
    render()
  }
  function close() {
    overlay!.classList.remove('open')
    document.body.style.overflow = ''
  }

  document.querySelectorAll('a[href="#waitlist"]').forEach((a) => {
    a.addEventListener('click', (e) => {
      e.preventDefault()
      open()
    })
  })
  document.getElementById('tfClose')!.addEventListener('click', close)
  prevB.addEventListener('click', back)
  nextB.addEventListener('click', advance)
  document.addEventListener('keydown', (e) => {
    if (!overlay.classList.contains('open')) return
    if (e.key === 'Escape') {
      close()
      return
    }
    const Q = QS[i]
    if (!Q) return
    if ((Q.type === 'single' || Q.type === 'multi') && /^[a-zA-Z]$/.test(e.key)) {
      const idx = LETTERS.indexOf(e.key.toUpperCase())
      if (idx >= 0 && idx < (Q.options?.length ?? 0)) {
        const btn = stage.querySelectorAll<HTMLElement>('.tf-opt')[idx]
        if (btn) btn.click()
      }
    }
    if (e.key === 'Enter' && (Q.type === 'single' || Q.type === 'multi')) {
      e.preventDefault()
      advance()
    }
  })
}

// `Question` is re-exported for consumers that build custom flows.
export type { Question }
