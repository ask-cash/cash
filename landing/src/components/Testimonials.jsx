import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

const testimonials = [
  {
    quote: 'I did NOT wake up at 4:30 AM for this. Sign up already.',
    name: 'Cash',
    title: 'Chief Judging Officer',
    emoji: '😾',
  },
  {
    quote: "He asked me to remind him about leg day. It's been 47 days. I'm still reminding him.",
    name: 'Cash',
    title: 'Fitness Accountability Cat',
    emoji: '🏋️',
  },
  {
    quote: "I remember everything. EVERYTHING. That thing you said 3 weeks ago? Yeah, I have it logged.",
    name: 'Cash',
    title: 'Memory Department',
    emoji: '🧠',
  },
]

export default function Testimonials() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section ref={ref} className="py-24 md:py-32 border-t border-border-subtle">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div
          className="text-center mb-16"
          initial={{ opacity: 0, y: 16 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
            What my friends say about Cash
          </h2>
          <p className="text-text-secondary">
            (I don't have friends. These are all Cash.)
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {testimonials.map((t, i) => (
            <motion.div
              key={i}
              className="p-8 rounded-2xl border border-border-subtle bg-bg hover:border-border hover:shadow-sm transition-all duration-300 group"
              initial={{ opacity: 0, y: 20 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: i * 0.1 }}
              whileHover={{ y: -4, transition: { duration: 0.2 } }}
            >
              <span className="text-3xl mb-6 block">{t.emoji}</span>
              <p className="text-text leading-relaxed mb-8">"{t.quote}"</p>
              <div className="border-t border-border-subtle pt-4">
                <p className="font-semibold text-sm">{t.name}</p>
                <p className="text-xs text-text-tertiary">{t.title}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
