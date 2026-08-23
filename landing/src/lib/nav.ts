// Nav: shadow-on-scroll and the mobile drawer.
const BURGER =
  '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>'
const CLOSE =
  '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>'

export function initNav() {
  const nav = document.getElementById('nav')
  if (nav) {
    const onScroll = () => nav.classList.toggle('scrolled', window.scrollY > 12)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
  }

  const navToggle = document.getElementById('navToggle')
  const navDrawer = document.getElementById('navLinksMobile')
  if (navToggle && navDrawer) {
    const setMenu = (open: boolean) => {
      navDrawer.classList.toggle('open', open)
      navToggle.classList.toggle('open', open)
      navToggle.innerHTML = open ? CLOSE : BURGER
      navToggle.setAttribute('aria-expanded', open ? 'true' : 'false')
    }
    navToggle.addEventListener('click', () => setMenu(!navDrawer.classList.contains('open')))
    navDrawer.addEventListener('click', (e) => {
      if ((e.target as HTMLElement).closest('a')) setMenu(false)
    })
    window.addEventListener(
      'scroll',
      () => {
        if (navDrawer.classList.contains('open')) setMenu(false)
      },
      { passive: true },
    )
  }
}
