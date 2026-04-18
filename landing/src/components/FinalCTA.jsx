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
        <p className="font-display text-[0.74rem] font-semibold text-[#ffa0ac] uppercase tracking-[0.28em] mb-5">
          Adoption
        </p>

        <h2 className="font-display text-3xl md:text-5xl font-bold tracking-tight leading-[1.05]">
          Pick a pet.
        </h2>

        <p className="mt-5 text-[#a8b0c0] text-base md:text-[1.05rem] leading-relaxed">
          Cash is off the market (signed the contract in salmon ink). Her litter
          isn&apos;t — hop on the list and she&apos;ll intro you. Or invent your
          own weird little beast from scratch.
        </p>

        <form
          className="mt-10 flex flex-col sm:flex-row gap-2 max-w-md mx-auto"
          onSubmit={(e) => e.preventDefault()}
        >
          <input
            className="flex-1 min-w-0 bg-white/[0.04] border border-white/12 rounded-full px-5 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-[#ff6e80]/35 focus:border-[#ff6e80] transition-all duration-200 placeholder:text-white/40 backdrop-blur"
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
              background: 'linear-gradient(135deg, #ff6e80 0%, #c72e4a 100%)',
              boxShadow:
                '0 6px 24px rgba(255,110,128,0.45), inset 0 1px 0 rgba(255,255,255,0.18)',
            }}
          >
            Join waitlist
          </motion.button>
        </form>

        <p className="mt-4 text-[#6b7480] text-xs">
          No spam. Your pet will handle the important judgment.
        </p>
      </motion.div>
    </section>
  )
}
