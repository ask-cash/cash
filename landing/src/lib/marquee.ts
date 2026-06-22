// Integrations marquee — three rows scrolling in alternating directions, built
// directly from the integration data (each row's content is duplicated so the
// CSS translateX(-50%) loop is seamless).
import { INTEGR } from '../data/integrations'

export function initMarquee() {
  const pill = (x: { n: string; src: string }) =>
    '<div class="imq-pill"><img src="' + x.src + '" alt=""><span>' + x.n + '</span></div>'
  const rep = <T,>(a: T[], n: number): T[] => {
    let o: T[] = []
    for (let k = 0; k < n; k++) o = o.concat(a)
    return o
  }
  const fill = (id: string, arr: typeof INTEGR) => {
    const el = document.getElementById(id)
    if (!el) return
    const h = arr.map(pill).join('')
    el.innerHTML = '<div class="imq-track">' + h + h + '</div>'
  }

  const g1 = INTEGR.filter((_, i) => i % 3 === 0)
  const g2 = INTEGR.filter((_, i) => i % 3 === 1)
  const g3 = INTEGR.filter((_, i) => i % 3 === 2)
  fill('imqRow1', rep(g1, 4))
  fill('imqRow2', rep(g2, 4))
  fill('imqRow3', rep(g3, 4))
}
