import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { useScrollReveal } from '../hooks/useScrollReveal'
import CashMascotEmbed from './CashMascotEmbed'

const CASH_MESSAGE =
  "My human can't shut up about AI, so I work here for treats. But I have friends — smart AI cats looking for humans to run. Join the waitlist; I'll introduce you."

function TypingDots() {
  return (
    <div className="inline-flex items-center gap-[4px] py-[3px]">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-black/40"
          animate={{ y: [0, -3, 0], opacity: [0.4, 1, 0.4] }}
          transition={{
            duration: 0.95,
            repeat: Infinity,
            delay: i * 0.15,
            ease: 'easeInOut',
          }}
        />
      ))}
    </div>
  )
}

function ChatWindow({ isInView }) {
  // 0: nothing, 1: typing dots, 2: message shown, 3: delivered label shown
  const [step, setStep] = useState(0)

  useEffect(() => {
    if (!isInView) return
    setStep(0)
    const t1 = setTimeout(() => setStep(1), 600)
    const t2 = setTimeout(() => setStep(2), 2100)
    const t3 = setTimeout(() => setStep(3), 2700)
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
      clearTimeout(t3)
    }
  }, [isInView])

  return (
    <motion.div
      initial={{ opacity: 0, y: 24, scale: 0.98 }}
      animate={isInView ? { opacity: 1, y: 0, scale: 1 } : {}}
      transition={{ duration: 0.55, ease: 'easeOut' }}
      className="max-w-[420px] mx-auto rounded-[32px] border border-black/[0.08] bg-white shadow-[0_30px_80px_-20px_rgba(0,0,0,0.22),0_8px_24px_-8px_rgba(0,0,0,0.08)] overflow-hidden"
    >
      <div className="flex flex-col items-center gap-2.5 px-5 pt-6 pb-5 bg-gradient-to-b from-[#f6f6f8] to-white border-b border-black/[0.06]">
        <div className="relative">
          <motion.div
            className="w-14 h-14 rounded-full flex items-center justify-center shadow-[0_4px_14px_rgba(249,115,22,0.28)]"
            style={{
              background: 'linear-gradient(135deg, #fed7aa 0%, #fdba74 100%)',
            }}
            animate={{ rotate: [0, -4, 4, 0] }}
            transition={{
              duration: 1.6,
              repeat: Infinity,
              repeatDelay: 3.5,
              ease: 'easeInOut',
            }}
          >
            <motion.span
              className="text-[1.75rem] leading-none inline-block"
              aria-hidden
              animate={{ rotate: [0, 10, -10, 0] }}
              transition={{
                duration: 1.4,
                repeat: Infinity,
                repeatDelay: 2.5,
                ease: 'easeInOut',
              }}
            >
              😼
            </motion.span>
          </motion.div>
          <span className="absolute -bottom-0.5 -right-0.5 flex w-3.5 h-3.5">
            <span className="absolute inset-0 rounded-full bg-[#10b981] opacity-60 animate-ping" />
            <span className="relative w-3.5 h-3.5 rounded-full bg-[#10b981] ring-[2.5px] ring-white" />
          </span>
        </div>
        <div className="text-center">
          <p className="font-semibold text-[0.95rem] text-black leading-none tracking-tight">
            Cash
          </p>
          <motion.p
            className="mt-1.5 text-[0.72rem] text-black/40 leading-none"
            animate={{ opacity: step === 1 ? [0.4, 1, 0.4] : 0.4 }}
            transition={{
              duration: 1.2,
              repeat: step === 1 ? Infinity : 0,
              ease: 'easeInOut',
            }}
          >
            {step === 1 ? 'typing…' : 'active now'}
          </motion.p>
        </div>
      </div>

      <div className="px-4 py-6 min-h-[240px] bg-white flex flex-col">
        <motion.p
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          transition={{ duration: 0.4, delay: 0.2 }}
          className="text-center text-[0.7rem] text-black/40 font-medium mb-3 tracking-tight"
        >
          <span className="font-semibold text-black/55">Today</span> 10:47 AM
        </motion.p>

        <AnimatePresence mode="wait">
          {step === 1 && (
            <motion.div
              key="typing"
              initial={{ opacity: 0, y: 6, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.15 } }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="self-start bg-[#e9e9eb] rounded-[20px] px-3.5 py-2"
            >
              <TypingDots />
            </motion.div>
          )}

          {step >= 2 && (
            <motion.div
              key="message"
              initial={{ opacity: 0, y: 10, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              className="imessage-bubble self-start max-w-[85%] bg-[#e9e9eb] rounded-[20px] px-[14px] py-[9px] text-[0.95rem] leading-[1.38] text-black"
            >
              {CASH_MESSAGE}{' '}
              <motion.span
                className="inline-block"
                animate={{ rotate: [0, 18, -18, 0] }}
                transition={{
                  duration: 1.4,
                  repeat: Infinity,
                  repeatDelay: 2,
                  ease: 'easeInOut',
                }}
              >
                😼
              </motion.span>
            </motion.div>
          )}
        </AnimatePresence>

        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: step >= 3 ? 1 : 0 }}
          transition={{ duration: 0.3 }}
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
          <h2 className="font-display font-bold text-2xl sm:text-3xl md:text-4xl tracking-tight leading-[1.05]">
            A message from your{' '}
            <span className="hero-title-gradient">cat.</span>
          </h2>
          <p className="mt-4 text-[#5c2e0a] text-sm sm:text-base">
            She has thoughts.
          </p>
        </motion.div>

        <ChatWindow isInView={isInView} />
      </div>
    </section>
  )
}
