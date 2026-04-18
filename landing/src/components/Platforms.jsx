import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

const platforms = [
  { name: 'Telegram', icon: 'https://cdn.simpleicons.org/telegram/26A5E4', desc: 'Where Cash was born. Home turf.', available: true },
  { name: 'WhatsApp', icon: 'https://cdn.simpleicons.org/whatsapp/25D366', desc: 'Blue ticks of judgment.' },
  { name: 'iMessage', emoji: '💬', desc: 'Blue bubbles only.' },
  { name: 'Discord', icon: 'https://cdn.simpleicons.org/discord/5865F2', desc: 'Judgment in your server.' },
  { name: 'X DMs', icon: 'https://cdn.simpleicons.org/x/ffffff', desc: 'Roasts in 280 characters.' },
]

export default function Platforms() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section ref={ref} className="relative py-24 md:py-32 text-[#f1f3f9]">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div
          className="text-center mb-14"
          initial={{ opacity: 0, y: 16 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <p className="font-display text-[0.78rem] sm:text-[0.82rem] font-medium text-[#7fa9ff] uppercase tracking-[0.22em] mb-4 inline-flex items-center gap-2">
            <span className="text-[#7fa9ff]" aria-hidden>
              ⟩
            </span>
            Anywhere you chat
          </p>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-3 font-display text-[#f1f3f9]">
            Talk to Cash wherever you hide
          </h2>
          <p className="text-[#a8b0c0]">She'll find you. She always does.</p>
        </motion.div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          {platforms.map((p, i) => (
            <motion.div
              key={p.name}
              className="p-6 rounded-2xl border border-white/10 bg-white/[0.04] backdrop-blur-md hover:border-[#4f8eff]/45 hover:bg-white/[0.07] hover:shadow-[0_14px_36px_-12px_rgba(79,142,255,0.45)] transition-all duration-300 text-center relative overflow-hidden"
              initial={{ opacity: 0, y: 20 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.08 }}
              whileHover={{ y: -4, transition: { duration: 0.2 } }}
            >
              {p.available ? (
                <div className="absolute top-2.5 right-2.5 w-2 h-2 rounded-full bg-[#10b981] shadow-[0_0_8px_rgba(16,185,129,0.7)]" title="Available now" />
              ) : (
                <div className="absolute top-2.5 right-2.5 w-2 h-2 rounded-full bg-white/25" title="Coming soon" />
              )}
              {p.icon ? (
                <img src={p.icon} alt={p.name} className="w-8 h-8 mx-auto mb-4" loading="lazy" />
              ) : (
                <span className="text-3xl mb-4 block">{p.emoji}</span>
              )}
              <h4 className="font-semibold text-sm mb-1 text-[#f1f3f9]">{p.name}</h4>
              <p className="text-xs text-[#a8b0c0]">{p.desc}</p>
              <p className="text-[10px] text-[#6b7480] mt-3 uppercase tracking-wider font-medium">
                {p.available ? 'Available' : 'Coming soon'}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
