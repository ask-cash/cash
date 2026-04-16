import { motion } from 'framer-motion'
import { useState, useEffect } from 'react'

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 10)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <motion.nav
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
      className={`fixed top-0 w-full z-50 transition-all duration-300 ${
        scrolled ? 'bg-white/80 backdrop-blur-xl border-b border-border' : 'bg-transparent'
      }`}
    >
      <div className="flex justify-between items-center max-w-6xl mx-auto px-6 py-4">
        <a href="#" className="text-lg font-bold tracking-tight text-text flex items-center gap-2">
          <span className="text-xl">😼</span>
          Cash
        </a>

        <div className="hidden md:flex items-center gap-8">
          <a className="text-sm text-text-secondary hover:text-text transition-colors duration-200" href="#features">Features</a>
          <a className="text-sm text-text-secondary hover:text-text transition-colors duration-200" href="#friends">Friends</a>
          <a className="text-sm text-text-secondary hover:text-text transition-colors duration-200" href="#integrations">Integrations</a>
          <a
            href="https://x.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-text-secondary hover:text-text transition-colors duration-200"
          >
            X (Twitter)
          </a>
        </div>

        <div className="flex items-center gap-3">
          <a href="#waitlist" className="text-sm font-medium text-text-secondary hover:text-text transition-colors duration-200 hidden sm:block">
            Log In
          </a>
          <motion.a
            href="#waitlist"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="bg-bg-dark text-text-inverse text-sm font-medium px-5 py-2.5 rounded-full hover:bg-neutral-800 transition-colors duration-200"
          >
            Join Waitlist
          </motion.a>
        </div>
      </div>
    </motion.nav>
  )
}
