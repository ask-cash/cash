import { initDotScatter } from './dotScatter'

// Footer wordmark: the dots fly in from their scattered start positions when the
// footer comes into view, settle into "cash", then idle-drift. Hovering pushes
// them apart.
export function initFooterMark() {
  const mark = document.getElementById('ftMark') as SVGSVGElement | null
  if (!mark) return

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return
        io.disconnect()
        mark.classList.add('in')
        // let the scatter-in transition land before the idle drift takes over
        setTimeout(() => mark.classList.add('drift'), 1700)
      })
    },
    { threshold: 0.15 },
  )
  io.observe(mark)

  initDotScatter(mark, '.ft-dots circle', { radius: 340, push: 54, falloff: 1.7 })
}
