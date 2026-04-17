import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

const HUB = { x: 12, y: 50 }
const TRUNK_START = 12
const TRUNK_END = 94
const TRUNK_Y = 50
const TRUNK_START_DELAY = 0.5
const TRUNK_DURATION = 1.4

// Sorted left-to-right so branches reveal in order as the trunk draws
const integrations = [
  {
    name: 'Google Drive',
    icon: 'https://cdn.simpleicons.org/googledrive/4285F4',
    x: 22,
    y: 86,
  },
  {
    name: 'Google Calendar',
    icon: 'https://cdn.simpleicons.org/googlecalendar/4285F4',
    x: 30,
    y: 14,
  },
  {
    name: 'Notion',
    icon: 'https://cdn.simpleicons.org/notion/000000',
    x: 42,
    y: 86,
  },
  {
    name: 'Gmail',
    icon: 'https://cdn.simpleicons.org/gmail/EA4335',
    x: 50,
    y: 14,
  },
  {
    name: 'Outlook',
    icon: 'https://cdn.simpleicons.org/microsoftoutlook/0078D4',
    x: 60,
    y: 86,
  },
  {
    name: 'Slack',
    icon: 'https://cdn.simpleicons.org/slack/E01E5A',
    x: 68,
    y: 14,
  },
  {
    name: 'X / Twitter',
    icon: 'https://cdn.simpleicons.org/x/000000',
    x: 78,
    y: 86,
  },
  {
    name: 'GitHub',
    icon: 'https://cdn.simpleicons.org/github/000000',
    x: 86,
    y: 14,
  },
  {
    name: 'Spotify',
    icon: 'https://cdn.simpleicons.org/spotify/1DB954',
    x: 92,
    y: 86,
  },
]

function branchDelay(x) {
  const t = (x - TRUNK_START) / (TRUNK_END - TRUNK_START)
  return TRUNK_START_DELAY + t * TRUNK_DURATION
}

export default function Integrations() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section
      id="integrations"
      ref={ref}
      className="relative py-20 md:py-28 text-[#1a0f05] overflow-hidden border-t border-[rgba(124,45,18,0.1)]"
      style={{
        background:
          'radial-gradient(1100px circle at 10% 0%, rgba(249,115,22,0.06), transparent 55%), radial-gradient(900px circle at 90% 100%, rgba(217,119,6,0.05), transparent 55%), #ffffff',
      }}
    >
      <div className="max-w-[1100px] mx-auto px-6">
        <motion.div
          className="text-center mb-12 md:mb-14"
          initial={{ opacity: 0, y: 14 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <p className="font-display text-[0.78rem] sm:text-[0.82rem] font-medium text-[#c2410c] uppercase tracking-[0.22em] mb-4 inline-flex items-center gap-2">
            <span className="text-[#f97316]" aria-hidden>
              ⟩
            </span>
            Integrations
          </p>
          <h2 className="font-display font-bold text-2xl sm:text-3xl md:text-4xl tracking-tight leading-[1.05]">
            Her paws in{' '}
            <span className="hero-title-gradient">everything.</span>
          </h2>
          <p className="mt-4 text-[#5c2e0a] text-sm sm:text-base">
            Cash hooks into the tools you pretend to be productive with.
          </p>
        </motion.div>

        <div className="hidden md:block relative h-[420px] lg:h-[460px]">
          <svg
            className="absolute inset-0 w-full h-full pointer-events-none"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            aria-hidden
          >
            <motion.line
              x1={TRUNK_START}
              y1={TRUNK_Y}
              x2={TRUNK_END}
              y2={TRUNK_Y}
              stroke="#f97316"
              strokeOpacity={0.55}
              strokeWidth={1.25}
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
              initial={{ pathLength: 0 }}
              animate={isInView ? { pathLength: 1 } : { pathLength: 0 }}
              transition={{
                duration: TRUNK_DURATION,
                delay: TRUNK_START_DELAY,
                ease: [0.65, 0, 0.35, 1],
              }}
            />

            {integrations.map((it) => (
              <motion.line
                key={`branch-${it.name}`}
                x1={it.x}
                y1={TRUNK_Y}
                x2={it.x}
                y2={it.y}
                stroke="#f97316"
                strokeOpacity={0.5}
                strokeWidth={1.25}
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
                initial={{ pathLength: 0 }}
                animate={isInView ? { pathLength: 1 } : { pathLength: 0 }}
                transition={{
                  duration: 0.32,
                  delay: branchDelay(it.x),
                  ease: 'easeOut',
                }}
              />
            ))}

            {integrations.map((it) => (
              <motion.circle
                key={`joint-${it.name}`}
                cx={it.x}
                cy={TRUNK_Y}
                r={0.9}
                fill="#f97316"
                vectorEffect="non-scaling-stroke"
                initial={{ opacity: 0, scale: 0 }}
                animate={isInView ? { opacity: 1, scale: 1 } : {}}
                transition={{
                  duration: 0.2,
                  delay: branchDelay(it.x),
                  ease: 'easeOut',
                }}
              />
            ))}
          </svg>

          <motion.div
            className="absolute -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${HUB.x}%`, top: `${HUB.y}%` }}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={isInView ? { opacity: 1, scale: 1 } : {}}
            transition={{ duration: 0.5, delay: 0.1, ease: 'easeOut' }}
          >
            <div className="relative flex flex-col items-center">
              <motion.span
                className="absolute -inset-4 rounded-full"
                style={{
                  background:
                    'radial-gradient(circle, rgba(249,115,22,0.35) 0%, transparent 70%)',
                }}
                animate={{ scale: [1, 1.25, 1], opacity: [0.6, 0.25, 0.6] }}
                transition={{
                  duration: 3,
                  repeat: Infinity,
                  ease: 'easeInOut',
                }}
              />
              <motion.div
                className="relative w-[96px] h-[96px] rounded-full flex items-center justify-center shadow-[0_12px_40px_rgba(249,115,22,0.38)] ring-[3px] ring-white"
                style={{
                  background:
                    'linear-gradient(135deg, #fed7aa 0%, #fdba74 100%)',
                }}
                animate={{ rotate: [0, -4, 4, 0] }}
                transition={{
                  duration: 1.6,
                  repeat: Infinity,
                  repeatDelay: 3,
                  ease: 'easeInOut',
                }}
              >
                <span className="text-[3rem] leading-none" aria-hidden>
                  😼
                </span>
                <span className="absolute -bottom-0.5 -right-0.5 flex w-3.5 h-3.5">
                  <span className="absolute inset-0 rounded-full bg-[#10b981] opacity-60 animate-ping" />
                  <span className="relative w-3.5 h-3.5 rounded-full bg-[#10b981] ring-[2.5px] ring-white" />
                </span>
              </motion.div>
              <p className="mt-3 font-display font-bold text-[0.72rem] text-[#c2410c] uppercase tracking-[0.18em]">
                Cash
              </p>
            </div>
          </motion.div>

          {integrations.map((it) => {
            const delay = branchDelay(it.x) + 0.28
            return (
              <motion.div
                key={it.name}
                className="absolute -translate-x-1/2 -translate-y-1/2 flex items-center gap-2 px-3.5 py-2 rounded-full bg-white border border-[rgba(124,45,18,0.18)] shadow-[0_4px_16px_rgba(124,45,18,0.08)] cursor-default"
                style={{ left: `${it.x}%`, top: `${it.y}%` }}
                initial={{ opacity: 0, scale: 0.5, y: it.y > TRUNK_Y ? -6 : 6 }}
                animate={
                  isInView
                    ? { opacity: 1, scale: 1, y: 0 }
                    : { opacity: 0, scale: 0.5 }
                }
                transition={{
                  duration: 0.4,
                  delay,
                  ease: [0.25, 1.25, 0.4, 1],
                }}
                whileHover={{
                  y: -2,
                  borderColor: 'rgba(249,115,22,0.6)',
                  boxShadow: '0 10px 24px rgba(249,115,22,0.2)',
                }}
              >
                <img
                  src={it.icon}
                  alt={it.name}
                  className="w-4 h-4 shrink-0"
                  loading="lazy"
                />
                <span className="text-[0.78rem] font-medium text-[#1a0f05] whitespace-nowrap">
                  {it.name}
                </span>
              </motion.div>
            )
          })}
        </div>

        <motion.div
          className="md:hidden flex flex-wrap justify-center gap-2.5"
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          {integrations.map((item, i) => (
            <motion.div
              key={item.name}
              className="flex items-center gap-2 px-3.5 py-2 rounded-full bg-white border border-[rgba(124,45,18,0.18)] shadow-sm"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={isInView ? { opacity: 1, scale: 1 } : {}}
              transition={{ duration: 0.3, delay: 0.25 + i * 0.04 }}
            >
              <img
                src={item.icon}
                alt={item.name}
                className="w-4 h-4"
                loading="lazy"
              />
              <span className="text-[0.78rem] font-medium text-[#1a0f05]">
                {item.name}
              </span>
            </motion.div>
          ))}
        </motion.div>

        <p className="mt-12 text-center text-[#8c5a2a] text-xs">
          More integrations coming. Cash demands access to your entire digital
          life.
        </p>
      </div>
    </section>
  )
}
</parameter>
</invoke>