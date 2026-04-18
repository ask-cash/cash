import { AnimatePresence, motion } from 'framer-motion'
import { useState, useEffect } from 'react'

export default function Navbar() {
  const [heroCtaVisible, setHeroCtaVisible] = useState(true)

  useEffect(() => {
    const el = document.getElementById('waitlist')
    if (!el) return
    const io = new IntersectionObserver(
      ([entry]) => setHeroCtaVisible(entry.isIntersecting),
      { threshold: 0, rootMargin: '-24px 0px 0px 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  return (
    <AnimatePresence>
      {!heroCtaVisible && (
        <motion.div
          key="floating-cta"
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -16 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          className="fixed top-0 inset-x-0 z-50 pointer-events-none"
        >
          <div className="max-w-[860px] mx-auto px-6 pt-4 flex justify-center">
            <motion.a
              href="#waitlist"
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.98 }}
              className="pointer-events-auto font-display text-sm font-semibold text-white px-5 py-2.5 rounded-full"
              style={{
                background: 'linear-gradient(135deg, #4f8eff 0%, #0050cc 100%)',
                boxShadow:
                  '0 6px 24px rgba(79,142,255,0.45), inset 0 1px 0 rgba(255,255,255,0.18)',
              }}
            >
              Join Waitlist
            </motion.a>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
