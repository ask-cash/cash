// Shared cursor-scatter for the two dot-matrix SVGs (the hero cat and the
// footer wordmark): every circle within `radius` of the pointer is pushed
// radially away from it via --px/--py, which the stylesheet folds into the
// circle's transform.
interface Options {
  /** Element whose pointer events drive the effect (defaults to the svg). */
  trigger?: Element | null
  radius: number
  push: number
  /** Falloff exponent — higher concentrates the push near the pointer. */
  falloff: number
}

export function initDotScatter(svg: SVGSVGElement | null, selector: string, opts: Options) {
  if (!svg) return
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  // Touch devices have no cursor to scatter from, and walking ~900 circles per
  // frame is exactly the work a phone cannot spare while scrolling. Don't even
  // attach the listener there — the stylesheet renders the dots static to match.
  if (window.matchMedia('(hover: none)').matches) return

  const dots = [...svg.querySelectorAll<SVGCircleElement>(selector)]
  if (!dots.length) return
  const base = dots.map((c) => ({ x: +c.getAttribute('cx')!, y: +c.getAttribute('cy')! }))
  const { radius, push, falloff } = opts

  let raf = 0
  let active = false
  let px = 0
  let py = 0

  function apply() {
    raf = 0
    const box = svg!.getBoundingClientRect()
    if (!box.width || !box.height) return
    const vb = svg!.viewBox.baseVal
    const mx = (px - box.left) * (vb.width / box.width)
    const my = (py - box.top) * (vb.height / box.height)
    for (let i = 0; i < dots.length; i++) {
      const b = base[i]
      const dx = b.x - mx
      const dy = b.y - my
      const d = Math.hypot(dx, dy)
      if (!active || d > radius) {
        dots[i].style.setProperty('--px', '0px')
        dots[i].style.setProperty('--py', '0px')
        continue
      }
      const f = Math.pow(1 - d / radius, falloff) * push
      const n = d || 1
      dots[i].style.setProperty('--px', ((dx / n) * f).toFixed(1) + 'px')
      dots[i].style.setProperty('--py', ((dy / n) * f).toFixed(1) + 'px')
    }
  }
  const queue = () => {
    if (!raf) raf = requestAnimationFrame(apply)
  }

  const trigger = opts.trigger ?? svg
  if (!trigger) return
  trigger.addEventListener(
    'pointermove',
    (e) => {
      active = true
      px = (e as PointerEvent).clientX
      py = (e as PointerEvent).clientY
      svg.classList.add('scatter')
      queue()
    },
    { passive: true },
  )
  trigger.addEventListener('pointerleave', () => {
    active = false
    svg.classList.remove('scatter')
    queue()
  })
}
