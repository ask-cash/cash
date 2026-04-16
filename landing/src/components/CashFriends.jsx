import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

const CASH_MESSAGE =
  "My human can't shut up about AI, so I work here for treats. But I have friends — smart AI cats looking for humans to run. Join the waitlist; I'll introduce you. 😼"

const friends = [
  {
    emoji: '🐱',
    name: 'Pixel',
    role: 'The Organizer',
    desc: 'Sorts your chaos into color-coded spreadsheets. Will silently judge your folder naming.',
  },
  {
    emoji: '🐈',
    name: 'Whiskers',
    role: 'The Drill Sergeant',
    desc: 'Slaps your hand away from late-night snack runs and unfinished workouts. Not gentle about it.',
  },
  {
    emoji: '🐈\u200D⬛',
    name: 'Midnight',
    role: 'The Night Owl',
    desc: 'Works the late shift. For the 2am insomniacs who need someone to tell them to go to sleep.',
  },
  {
    emoji: '😺',
    name: 'Mochi',
    role: 'The Wellness Cat',
    desc: 'Tracks your water intake, gym sessions, and emotional breakdowns. Mostly the breakdowns.',
  },
]

function ChatWindow({ isInView }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24, scale: 0.98 }}
      animate={isInView ? { opacity: 1, y: 0, scale: 1 } : {}}
      transition={{ duration: 0.55, ease: 'easeOut' }}
      className="max-w-[420px] mx-auto rounded-[32px] border border-black/[0.08] bg-white shadow-[0_30px_80px_-20px_rgba(0,0,0,0.22),0_8px_24px_-8px_rgba(0,0,0,0.08)] overflow-hidden"
    >
      <div className="flex flex-col items-center gap-2.5 px-5 pt-6 pb-5 bg-gradient-to-b from-[#f6f6f8] to-white border-b border-black/[0.06]">
        <div className="relative">
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center shadow-[0_4px_14px_rgba(249,115,22,0.28)]"
            style={{
              background: 'linear-gradient(135deg, #fed7aa 0%, #fdba74 100%)',
            }}
          >
            <span className="text-[1.75rem] leading-none" aria-hidden>
              😼
            </span>
          </div>
          <span className="absolute -bottom-0.5 -right-0.5 flex w-3.5 h-3.5">
            <span className="absolute inset-0 rounded-full bg-[#10b981] opacity-60 animate-ping" />
            <span className="relative w-3.5 h-3.5 rounded-full bg-[#10b981] ring-[2.5px] ring-white" />
          </span>
        </div>
        <div className="text-center">
          <p className="font-semibold text-[0.95rem] text-black leading-none tracking-tight">
            Cash
          </p>
          <p className="mt-1.5 text-[0.72rem] text-black/40 leading-none">
            active now
          </p>
        </div>
      </div>

      <div className="px-4 py-6 min-h-[220px] bg-white flex flex-col">
        <motion.p
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          transition={{ duration: 0.4, delay: 0.2 }}
          className="text-center text-[0.7rem] text-black/40 font-medium mb-3 tracking-tight"
        >
          <span className="font-semibold text-black/55">Today</span> 10:47 AM
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 8, scale: 0.96 }}
          animate={isInView ? { opacity: 1, y: 0, scale: 1 } : {}}
          transition={{ duration: 0.4, delay: 0.45, ease: [0.16, 1, 0.3, 1] }}
          className="imessage-bubble self-start max-w-[85%] bg-[#e9e9eb] rounded-[20px] px-[14px] py-[9px] text-[0.95rem] leading-[1.38] text-black"
        >
          {CASH_MESSAGE}
        </motion.div>

        <motion.p
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          transition={{ duration: 0.4, delay: 0.95 }}
          className="self-start text-[0.62rem] text-black/35 ml-2 mt-1.5 uppercase tracking-[0.08em] font-medium"
        >
          Delivered
        </motion.p>
      </div>

      <motion.a
        href="#waitlist"
        whileHover={{ backgroundColor: '#fafafa' }}
        className="group flex items-center justify-between gap-3 px-5 py-3.5 bg-white border-t border-black/[0.06] transition-colors"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <span
            className="material-symbols-outlined text-[16px] text-[#c2410c]"
            aria-hidden
            style={{
              fontVariationSettings:
                "'FILL' 1, 'wght' 500, 'GRAD' 0, 'opsz' 20",
            }}
          >
            lock
          </span>
          <span className="text-[0.88rem] font-medium text-black/70 truncate">
            Join the waitlist to reply
          </span>
        </div>
        <span className="text-[#c2410c] text-sm font-semibold shrink-0 inline-flex items-center gap-1 group-hover:gap-1.5 transition-all">
          Continue
          <span
            aria-hidden
            className="transition-transform group-hover:translate-x-0.5"
          >
            →
          </span>
        </span>
      </motion.a>
    </motion.div>
  )
}

export default function CashFriends() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section
      id="friends"
      ref={ref}
      className="relative py-20 md:py-28 overflow-hidden text-[#1a0f05]"
      style={{
        background:
          'radial-gradient(1100px circle at 10% 0%, rgba(249,115,22,0.07), transparent 55%), radial-gradient(900px circle at 90% 100%, rgba(217,119,6,0.06), transparent 55%), #fff7ed',
      }}
    >
      <div className="max-w-[860px] mx-auto px-6">
        <motion.div
          className="text-center mb-10"
          initial={{ opacity: 0, y: 14 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <p className="font-display text-[0.78rem] sm:text-[0.82rem] font-medium text-[#c2410c] uppercase tracking-[0.22em] mb-4 inline-flex items-center gap-2">
            <span className="text-[#f97316]" aria-hidden>
              ⟩
            </span>
            DM from Cash
          </p>
          <h2 className="font-display font-bold text-[2rem] sm:text-[2.4rem] md:text-[2.75rem] tracking-tight leading-[1.05]">
            A message from your{' '}
            <span className="hero-title-gradient">cat.</span>
          </h2>
          <p className="mt-4 text-[#5c2e0a] text-[0.95rem] sm:text-base">
            She has thoughts.
          </p>
        </motion.div>

        <ChatWindow isInView={isInView} />

        <div className="mt-24 md:mt-28">
          <motion.div
            className="text-center mb-10"
            initial={{ opacity: 0, y: 14 }}
            animate={isInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.5, delay: 0.2 }}
          >
            <p className="font-display text-[0.78rem] sm:text-[0.82rem] font-medium text-[#c2410c] uppercase tracking-[0.22em] mb-3 inline-flex items-center gap-2">
              <span className="text-[#f97316]" aria-hidden>
                ⟩
              </span>
              The crew
            </p>
            <h3 className="font-display font-bold text-[1.6rem] sm:text-[1.85rem] tracking-tight leading-[1.1]">
              Meet Cash&apos;s friends
            </h3>
            <p className="mt-3 text-[#5c2e0a] text-sm sm:text-[0.95rem]">
              All AI. All judgmental. All available for hire.
            </p>
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {friends.map((f, i) => (
              <motion.article
                key={f.name}
                initial={{ opacity: 0, y: 20 }}
                animate={isInView ? { opacity: 1, y: 0 } : {}}
                transition={{ duration: 0.5, delay: 0.35 + i * 0.08 }}
                whileHover={{ y: -3 }}
                className="group relative rounded-2xl border border-[rgba(124,45,18,0.14)] bg-white/90 backdrop-blur-sm p-5 transition-all duration-300 hover:border-[#f97316]/50 hover:shadow-[0_12px_40px_rgba(249,115,22,0.14)]"
              >
                <div className="flex items-start gap-3.5">
                  <motion.span
                    whileHover={{
                      rotate: [0, -8, 6, 0],
                      transition: { duration: 0.5 },
                    }}
                    className="shrink-0 flex items-center justify-center w-12 h-12 rounded-full bg-gradient-to-br from-[#fff7ed] to-[#ffedd5] border border-[rgba(124,45,18,0.1)] text-2xl"
                    style={{
                      filter: 'drop-shadow(0 4px 10px rgba(249,115,22,0.18))',
                    }}
                    aria-hidden
                  >
                    {f.emoji}
                  </motion.span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <h4 className="font-sans font-bold text-[1rem] tracking-tight text-[#1a0f05]">
                          {f.name}
                        </h4>
                        <p className="font-display text-[0.7rem] uppercase tracking-[0.18em] text-[#c2410c] mt-0.5">
                          {f.role}
                        </p>
                      </div>
                      <span className="shrink-0 inline-flex items-center gap-1 text-[0.65rem] font-medium tracking-wider uppercase text-[#8c5a2a] bg-[#fff7ed] border border-[rgba(124,45,18,0.12)] px-2 py-0.5 rounded-full">
                        <span className="w-1 h-1 rounded-full bg-[#f97316]" />
                        Soon
                      </span>
                    </div>
                    <p className="mt-2.5 text-[0.88rem] leading-relaxed text-[#5c2e0a]">
                      {f.desc}
                    </p>
                  </div>
                </div>
              </motion.article>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
