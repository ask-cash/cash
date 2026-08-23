// FAQ accordion — one panel open at a time. The panel animates on max-height,
// so the height has to be measured from the rendered answer.
export function initFaq() {
  const list = document.getElementById('faqList')
  if (!list) return

  list.querySelectorAll<HTMLElement>('.f-item').forEach((item) => {
    const q = item.querySelector<HTMLElement>('.f-q')!
    const a = item.querySelector<HTMLElement>('.f-a')!
    q.addEventListener('click', () => {
      const isOpen = item.classList.contains('open')
      list.querySelectorAll<HTMLElement>('.f-item.open').forEach((o) => {
        o.classList.remove('open')
        o.querySelector<HTMLElement>('.f-a')!.style.maxHeight = '0px'
      })
      if (!isOpen) {
        item.classList.add('open')
        a.style.maxHeight = a.scrollHeight + 'px'
      }
    })
  })
}
