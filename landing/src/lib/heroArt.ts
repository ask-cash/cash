import { initDotScatter } from './dotScatter'

// The hero's dot-matrix cat. The idle drift is pure CSS; this only adds the
// cursor push, driven from anywhere in the hero rather than the artwork itself
// so the effect reaches the dots before you touch them.
export function initHeroArt() {
  const art = document.getElementById('heroArt') as SVGSVGElement | null
  initDotScatter(art, '.ha-dots circle', {
    trigger: document.querySelector('.hero'),
    radius: 150,
    push: 44,
    falloff: 1.6,
  })
}
