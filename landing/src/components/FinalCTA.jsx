import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

export default function FinalCTA() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section ref={ref} className="relative py-24 md:py-32 text-[#f1f3f9]">
      <motion.div
        className="max-w-xl mx-auto px-6 text-center"
        initial={{ opacity: 0, y: 20 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.55 }}
      >
        <p className="font-display text-[0.74rem] font-semibold text-[#7fa9ff] uppercase tracking-[0.28em] mb-5">
          Waitlist
        </p>

        <h2 className="font-display text-3xl md:text-5xl font-bold tracking-tight leading-[1.05]">
          Join the waitlist.
        </h2>

        <p className="mt-5 text-[#a8b0c0] text-base md:text-[1.05rem] leading-relaxed">
          Cash is still deciding which humans deserve her time. Get in line so
          she can judge you next.
        </p>

        <form
          className="mt-10 flex flex-col sm:flex-row gap-2 max-w-md mx-auto"
          onSubmit={(e) => e.preventDefault()}
        >
          <input
            className="flex-1 min-w-0 bg-white/[0.04] border border-white/12 rounded-full px-5 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-[#4f8eff]/35 focus:border-[#4f8eff] transition-all duration-200 placeholder:text-white/40 backdrop-blur"
            placeholder="you@domain.com"
            type="email"
            autoComplete="email"
          />
          <motion.button
            type="submit"
            whileHover={{ y: -1 }}
            whileTap={{ scale: 0.98 }}
            className="shrink-0 text-white text-sm font-semibold px-7 py-3 rounded-full transition-colors duration-200 whitespace-nowrap cursor-pointer"
            style={{
              background: 'linear-gradient(135deg, #4f8eff 0%, #0050cc 100%)',
              boxShadow:
                '0 6px 24px rgba(79,142,255,0.45), inset 0 1px 0 rgba(255,255,255,0.18)',
            }}
          >
            Join waitlist
          </motion.button>
        </form>

        <p className="mt-4 text-[#6b7480] text-xs">
          No spam. Cash will still judge you, but only about productivity.
        </p>
      </motion.div>
    </section>
  )
}
