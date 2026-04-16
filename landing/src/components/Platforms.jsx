import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

const platforms = [
  { name: 'Telegram', icon: 'https://cdn.simpleicons.org/telegram/26A5E4', desc: 'Where Cash was born. Home turf.', available: true },
  { name: 'WhatsApp', icon: 'https://cdn.simpleicons.org/whatsapp/25D366', desc: 'Blue ticks of judgment.' },
  { name: 'iMessage', emoji: '💬', desc: 'Blue bubbles only.' },
  { name: 'Discord', icon: 'https://cdn.simpleicons.org/discord/5865F2', desc: 'Judgment in your server.' },
  { name: 'X DMs', icon: 'https://cdn.simpleicons.org/x/000000', desc: 'Roasts in 280 characters.' },
]

export default function Platforms() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section ref={ref} className="py-24 md:py-32 border-t border-border-subtle">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div
          className="text-center mb-14"
          initial={{ opacity: 0, y: 16 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
            Talk to Cash wherever you hide
          </h2>
          <p className="text-text-secondary">She'll find you. She always does.</p>
        </motion.div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          {platforms.map((p, i) => (
            <motion.div
              key={p.name}
              className="p-6 rounded-2xl border border-border-subtle bg-white hover:border-border hover:shadow-sm transition-all duration-300 text-center relative overflow-hidden"
              initial={{ opacity: 0, y: 20 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.08 }}
              whileHover={{ y: -4, transition: { duration: 0.2 } }}
            >
              {p.available ? (
                <div className="absolute top-2.5 right-2.5 w-2 h-2 rounded-full bg-green-500" title="Available now" />
              ) : (
                <div className="absolute top-2.5 right-2.5 w-2 h-2 rounded-full bg-text-tertiary/30" title="Coming soon" />
              )}
              {p.icon ? (
                <img src={p.icon} alt={p.name} className="w-8 h-8 mx-auto mb-4" loading="lazy" />
              ) : (
                <span className="text-3xl mb-4 block">{p.emoji}</span>
              )}
              <h4 className="font-semibold text-sm mb-1">{p.name}</h4>
              <p className="text-xs text-text-tertiary">{p.desc}</p>
              <p className="text-[10px] text-text-tertiary mt-3 uppercase tracking-wider font-medium">
                {p.available ? 'Available' : 'Coming soon'}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
