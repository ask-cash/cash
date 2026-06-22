// Shared scroll-reveal observer. Elements with `.reveal` get `.in` once they
// enter the viewport. Returns the observer so other modules can observe nodes
// they create dynamically.
export function initReveal(): IntersectionObserver {
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) {
          en.target.classList.add('in')
          io.unobserve(en.target)
        }
      })
    },
    { threshold: 0.14, rootMargin: '0px 0px -8% 0px' },
  )
  document.querySelectorAll('.reveal').forEach((el) => io.observe(el))
  return io
}
