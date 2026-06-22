// Ethos spotlight: a soft glow tracks whichever sentence is nearest the
// viewport center as you scroll.
export function initEthos() {
  const ethosSpot = document.getElementById('ethosSpot')
  const ethosSection = document.getElementById('ethos')
  if (!ethosSpot || !ethosSection) return

  const updateSpot = () => {
    const sents = [...ethosSection.querySelectorAll('.ethos-sent')]
    const center = window.innerHeight / 2
    let best: Element | null = null
    let bestDist = Infinity
    sents.forEach((s) => {
      const r = s.getBoundingClientRect()
      const mid = r.top + r.height / 2
      const dist = Math.abs(mid - center)
      if (dist < bestDist) {
        bestDist = dist
        best = s
      }
    })
    if (best) {
      const sr = ethosSection.getBoundingClientRect()
      const br = (best as Element).getBoundingClientRect()
      ethosSpot.style.top = br.top + br.height / 2 - sr.top + 'px'
    }
  }
  updateSpot()
  window.addEventListener('scroll', updateSpot, { passive: true })
  window.addEventListener('resize', updateSpot)
}
