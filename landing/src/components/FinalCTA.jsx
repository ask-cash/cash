import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

export default function FinalCTA() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section ref={ref} className="py-24 md:py-32 bg-bg-dark text-text-inverse">
      <motion.div
        className="max-w-2xl mx-auto px-6 text-center"
        initial={{ opacity: 0, y: 20 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.6 }}
      >
        <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">
          You scrolled this far.
          <br />
          Just sign up.
        </h2>
        <p className="text-neutral-400 text-lg mb-10">
          Cash is watching. She knows you're interested.
        </p>

        <form className="flex flex-col sm:flex-row gap-3 max-w-md mx-auto mb-6" onSubmit={(e) => e.preventDefault()}>
          <input
            className="flex-1 bg-neutral-900 border border-neutral-700 rounded-full px-5 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-white/20 focus:border-neutral-500 transition-all duration-200 placeholder:text-neutral-500"
            placeholder="Your email address"
            type="email"
          />
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="bg-white text-bg-dark text-sm font-semibold px-7 py-3 rounded-full hover:bg-neutral-200 transition-colors duration-200 whitespace-nowrap cursor-pointer"
          >
            Join Waitlist
          </motion.button>
        </form>

        <p className="text-neutral-500 text-xs">
          Get your own AI cat assistant. Cash will assign one of her friends to judge your life specifically.
        </p>
      </motion.div>
    </section>
  )
}
