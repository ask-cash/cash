import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

export default function FinalCTA() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section
      ref={ref}
      className="relative py-24 md:py-32 text-[#f1f3f9] overflow-hidden"
    >
      {/* Subtle local glow so the CTA section feels lit, without breaking the unified bg */}
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(700px circle at 50% 30%, rgba(79,142,255,0.18), transparent 55%), radial-gradient(500px circle at 80% 100%, rgba(249,115,22,0.14), transparent 55%)',
        }}
      />
      <motion.div
        className="relative max-w-2xl mx-auto px-6 text-center"
        initial={{ opacity: 0, y: 20 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.6 }}
      >
        <h2 className="font-display text-3xl md:text-5xl font-bold tracking-tight mb-4">
          You scrolled this far.
          <br />
          Just sign up.
        </h2>
        <p className="text-[#a8b0c0] text-lg mb-10">
          Cash is watching. She knows you're interested.
        </p>

        <form className="flex flex-col sm:flex-row gap-3 max-w-md mx-auto mb-6" onSubmit={(e) => e.preventDefault()}>
          <input
            className="flex-1 bg-white/[0.05] border border-white/15 rounded-full px-5 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-[#4f8eff]/40 focus:border-[#4f8eff] transition-all duration-200 placeholder:text-white/40 backdrop-blur"
            placeholder="Your email address"
            type="email"
          />
          <motion.button
            whileHover={{ scale: 1.02, y: -1 }}
            whileTap={{ scale: 0.98 }}
            className="text-white text-sm font-semibold px-7 py-3 rounded-full transition-colors duration-200 whitespace-nowrap cursor-pointer"
            style={{
              background: 'linear-gradient(135deg, #4f8eff 0%, #0050cc 100%)',
              boxShadow:
                '0 6px 28px rgba(79,142,255,0.50), inset 0 1px 0 rgba(255,255,255,0.18)',
            }}
          >
            Join Waitlist
          </motion.button>
        </form>

        <p className="text-[#6b7480] text-xs">
          Get your own AI cat assistant. Cash will assign one of her friends to judge your life specifically.
        </p>
      </motion.div>
    </section>
  )
}
