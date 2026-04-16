import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

const features = [
  {
    icon: '🧠',
    title: 'Remembers everything',
    desc: "Say \"I'll quit sugar this week\" and she'll haunt you about it on day 3. She's like an elephant. But a cat.",
  },
  {
    icon: '📅',
    title: 'Calendar merge',
    desc: 'Google Calendar + Outlook in one view. She sees your schedule and has opinions about it.',
  },
  {
    icon: '⚡',
    title: 'Smart scheduling',
    desc: 'Auto-resolves conflicts. Moves gym when meetings collide. Guilt-trips you either way.',
  },
  {
    icon: '📊',
    title: 'Trading rules',
    desc: 'Recites your rules before market open. Roasts you if you break discipline.',
  },
  {
    icon: '✅',
    title: 'Task tracking',
    desc: "Unfinished tasks don't die, they follow you. There is no delete button, only accountability.",
  },
  {
    icon: '💬',
    title: 'Natural language',
    desc: "Just talk to her like a friend. She's judgy but she understands. Claude AI powers her brain.",
  },
]

export default function Features() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section id="features" ref={ref} className="py-24 md:py-32 bg-bg-subtle border-t border-border-subtle">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div
          className="text-center mb-16"
          initial={{ opacity: 0, y: 16 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
            What Cash actually does
          </h2>
          <p className="text-text-secondary">Besides judging you.</p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((f, i) => (
            <motion.div
              key={i}
              className="p-8 rounded-2xl bg-white border border-border-subtle hover:border-border hover:shadow-sm transition-all duration-300 group"
              initial={{ opacity: 0, y: 20 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: i * 0.08 }}
              whileHover={{ y: -3, transition: { duration: 0.2 } }}
            >
              <span className="text-2xl mb-4 block">{f.icon}</span>
              <h3 className="text-lg font-semibold mb-2 tracking-tight">{f.title}</h3>
              <p className="text-sm text-text-secondary leading-relaxed">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
