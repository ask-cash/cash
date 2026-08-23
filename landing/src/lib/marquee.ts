// Integrations marquee — two rows scrolling in opposite directions. Each row's
// content is repeated so it is wide enough to fill any viewport, then doubled
// again so the CSS translateX(-50%) loop is seamless.
import { INTEGR, type Integration } from '../data/integrations'

const REPEAT = 5

export function initMarquee() {
  const pill = (x: Integration) =>
    '<div class="imq-pill"><img src="' + x.src + '" alt=""><span>' + x.n + '</span></div>'

  const rep = (a: Integration[], n: number): Integration[] => {
    let o: Integration[] = []
    for (let k = 0; k < n; k++) o = o.concat(a)
    return o
  }

  const fill = (id: string, arr: Integration[]) => {
    const el = document.getElementById(id)
    if (!el) return
    const h = arr.map(pill).join('')
    el.innerHTML = '<div class="imq-track">' + h + h + '</div>'
  }

  fill('imqRow1', rep(INTEGR.filter((_, i) => i % 2 === 0), REPEAT))
  fill('imqRow2', rep(INTEGR.filter((_, i) => i % 2 === 1), REPEAT))
}
