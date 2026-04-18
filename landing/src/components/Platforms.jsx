import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'
import CashMascotEmbed from './CashMascotEmbed'

const comingSoon = [
  {
    name: 'WhatsApp',
    icon: 'https://cdn.simpleicons.org/whatsapp/25D366',
    tint: '37, 211, 102',
    desc: 'Blue ticks of judgment.',
  },
  {
    name: 'iMessage',
    emoji: '💬',
    tint: '80, 160, 255',
    desc: 'Blue bubbles only.',
  },
  {
    name: 'Discord',
    icon: 'https://cdn.simpleicons.org/discord/5865F2',
    tint: '88, 101, 242',
    desc: 'Judgment in your server.',
  },
  {
    name: 'X DMs',
    icon: 'https://cdn.simpleicons.org/x/ffffff',
    tint: '220, 224, 230',
    desc: 'Roasts in 280 characters.',
  },
]

function SignalPing() {
  return (
    <span className="relative flex w-2 h-2">
      <span className="absolute inset-0 rounded-full bg-[#10b981] opacity-70 animate-ping" />
      <span className="relative w-2 h-2 rounded-full bg-[#10b981]" />
    </span>
  )
}

function TelegramFeature({ isInView }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 28 }}
      animate={isInView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.6, ease: [0.25, 0.4, 0.25, 1] }}
      className="relative rounded-3xl border border-[#26A5E4]/25 bg-white/[0.04] backdrop-blur-md overflow-hidden"
      style={{
        boxShadow:
          '0 30px 80px -20px rgba(38,165,228,0.35), inset 0 1px 0 rgba(255,255,255,0.06)',
      }}
    >
      {/* Ambient brand glow */}
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(700px circle at 15% 0%, rgba(38,165,228,0.22), transparent 55%), radial-gradient(500px circle at 100% 100%, rgba(79,142,255,0.14), transparent 55%)',
        }}
      />

      <div className="relative grid md:grid-cols-[1.1fr_1fr] gap-0">
        {/* Left: copy */}
        <div className="p-8 md:p-10 flex flex-col justify-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-[#26A5E4]/30 bg-[#26A5E4]/10 px-3 py-1 text-[0.68rem] font-display font-semibold uppercase tracking-[0.18em] text-[#7fc8ee] self-start">
            <SignalPing />
            Live now · Telegram
          </div>

          <h3 className="mt-5 font-display text-2xl md:text-[2rem] font-bold leading-[1.05] text-[#f1f3f9]">
            Cash lives in <br className="hidden md:block" />
            your Telegram.
          </h3>

          <p className="mt-4 text-[#a8b0c0] text-sm md:text-[0.95rem] leading-relaxed max-w-md">
            Where she was born. Home turf. Drop her a message and she&apos;ll
            start judging within seconds.
          </p>

          <motion.a
            href="https://t.me/"
            whileHover={{ x: 2 }}
            className="mt-7 inline-flex items-center gap-2 self-start text-[#7fc8ee] font-display font-semibold text-sm group"
          >
            <img
              src="https://cdn.simpleicons.org/telegram/26A5E4"
              alt=""
              aria-hidden
              className="w-4 h-4"
            />
            Open in Telegram
            <span
              aria-hidden
              className="transition-transform group-hover:translate-x-0.5"
            >
              →
            </span>
          </motion.a>
        </div>

        {/* Right: chat mock */}
        <div className="relative border-t md:border-t-0 md:border-l border-white/8 bg-[#06080f]/40 p-6 md:p-8">
          <div className="flex items-center gap-3 pb-4 border-b border-white/8">
            <div
              className="w-10 h-10 rounded-full flex items-center justify-center shrink-0"
              style={{
                background: 'linear-gradient(135deg, #fed7aa 0%, #fdba74 100%)',
                boxShadow: '0 0 20px rgba(249,115,22,0.35)',
              }}
            >
              <CashMascotEmbed className="w-7 h-6" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[0.92rem] font-semibold text-[#f1f3f9] leading-none">
                Cash
              </p>
              <p className="mt-1 text-[0.72rem] text-[#7fc8ee] leading-none flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#10b981]" />
                online · judging
              </p>
            </div>
            <img
              src="https://cdn.simpleicons.org/telegram/26A5E4"
              alt="Telegram"
              className="w-5 h-5 opacity-75"
            />
          </div>

          <div className="pt-5 space-y-2.5">
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: 0.35 }}
              className="flex justify-end"
            >
              <div className="max-w-[85%] rounded-[14px] rounded-br-[4px] bg-[#26A5E4] text-white text-[0.82rem] px-3 py-1.5 leading-snug shadow-[0_6px_20px_rgba(38,165,228,0.35)]">
                cash what&apos;s on my cal today
              </div>
            </motion.div>
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: 0.65 }}
              className="flex"
            >
              <div className="max-w-[88%] rounded-[14px] rounded-bl-[4px] bg-white/[0.08] border border-white/10 text-[#f1f3f9] text-[0.82rem] px-3 py-1.5 leading-snug backdrop-blur">
                three meetings you&apos;ll reschedule, a gym slot you&apos;ll
                skip, a &ldquo;quick&rdquo; email from tuesday. glad we talked.
              </div>
            </motion.div>
            <motion.p
              initial={{ opacity: 0 }}
              animate={isInView ? { opacity: 1 } : {}}
              transition={{ duration: 0.3, delay: 0.95 }}
              className="text-[0.62rem] text-[#6b7480] pl-1 uppercase tracking-[0.08em] font-medium"
            >
              Delivered · read
            </motion.p>
          </div>
        </div>
      </div>
    </motion.div>
  )
}

function ComingSoonTile({ p, i, isInView }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={isInView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.45, delay: 0.3 + i * 0.08 }}
      whileHover={{ y: -3 }}
      className="group relative rounded-2xl border border-white/10 bg-white/[0.03] backdrop-blur-md p-5 overflow-hidden transition-colors duration-300"
      style={{
        boxShadow: '0 6px 20px rgba(0,0,0,0.25)',
      }}
    >
      {/* Brand glow on hover */}
      <div
        aria-hidden
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
        style={{
          background: `radial-gradient(300px circle at 50% 0%, rgba(${p.tint}, 0.18), transparent 60%)`,
        }}
      />
      <div className="relative flex items-start justify-between mb-4">
        {p.icon ? (
          <img src={p.icon} alt={p.name} className="w-7 h-7" loading="lazy" />
        ) : (
          <span className="text-2xl leading-none">{p.emoji}</span>
        )}
        <span className="text-[0.58rem] font-display font-semibold uppercase tracking-[0.14em] text-[#6b7480] px-2 py-0.5 rounded-full border border-white/10">
          Soon
        </span>
      </div>
      <h4 className="relative font-display font-semibold text-sm text-[#f1f3f9] mb-1">
        {p.name}
      </h4>
      <p className="relative text-[0.75rem] leading-snug text-[#a8b0c0]">
        {p.desc}
      </p>
    </motion.div>
  )
}

export default function Platforms() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section ref={ref} className="relative py-24 md:py-32 text-[#f1f3f9]">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div
          className="text-center mb-12 md:mb-14"
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
          <h2 className="font-display text-3xl md:text-4xl font-bold tracking-tight mb-3 text-[#f1f3f9]">
            Talk to Cash wherever you hide
          </h2>
          <p className="text-[#a8b0c0] max-w-md mx-auto">
            She starts in Telegram. She&apos;ll find the rest of your inboxes
            soon enough.
          </p>
        </motion.div>

        <TelegramFeature isInView={isInView} />

        <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
          {comingSoon.map((p, i) => (
            <ComingSoonTile key={p.name} p={p} i={i} isInView={isInView} />
          ))}
        </div>
      </div>
    </section>
  )
}
