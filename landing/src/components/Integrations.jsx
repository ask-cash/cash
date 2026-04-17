import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

const VB_W = 180
const VB_H = 100

const HUB = {
  cx: 34,
  cy: 50,
  w: 40,
  h: 36,
}
const HUB_EXIT_X = HUB.cx + HUB.w / 2
const HUB_EXIT_Y = HUB.cy
const CTRL_X = 92
const NODE_X = 130

const integrations = [
  {
    name: 'Google Calendar',
    icon: 'https://cdn.simpleicons.org/googlecalendar/4285F4',
  },
  { name: 'Gmail', icon: 'https://cdn.simpleicons.org/gmail/EA4335' },
  {
    name: 'Google Drive',
    icon: 'https://cdn.simpleicons.org/googledrive/4285F4',
  },
  { name: 'Notion', icon: 'https://cdn.simpleicons.org/notion/000000' },
  { name: 'Slack', icon: 'https://api.iconify.design/logos/slack-icon.svg' },
  { name: 'X / Twitter', icon: 'https://cdn.simpleicons.org/x/000000' },
  { name: 'GitHub', icon: 'https://cdn.simpleicons.org/github/000000' },
  {
    name: 'Outlook',
    icon: 'https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/outlook.svg',
  },
  { name: 'Spotify', icon: 'https://cdn.simpleicons.org/spotify/1DB954' },
]

const N = integrations.length
const Y_START = 6
const Y_END = 94
const nodeY = (i) => Y_START + ((Y_END - Y_START) * i) / (N - 1)

function linePath(targetY) {
  return `M ${HUB_EXIT_X},${HUB_EXIT_Y} C ${CTRL_X},${HUB_EXIT_Y} ${CTRL_X},${targetY} ${NODE_X},${targetY}`
}

export default function Integrations() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section
      id="integrations"
      ref={ref}
      className="relative py-20 md:py-28 text-[#1a0f05] border-t border-[rgba(124,45,18,0.1)]"
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

        <div
          className="hidden md:block relative w-full max-w-[920px] mx-auto"
          style={{ aspectRatio: `${VB_W} / ${VB_H}` }}
        >
          <svg
            className="absolute inset-0 w-full h-full"
            viewBox={`0 0 ${VB_W} ${VB_H}`}
            preserveAspectRatio="none"
            aria-hidden
          >
            <defs>
              {integrations.map((_, i) => (
                <clipPath key={`cp-${i}`} id={`rev-line-${i}`}>
                  <motion.rect
                    x={HUB_EXIT_X}
                    y={0}
                    height={VB_H}
                    initial={{ width: 0 }}
                    animate={isInView ? { width: 100 } : { width: 0 }}
                    transition={{
                      duration: 0.75,
                      delay: 0.4 + i * 0.14,
                      ease: [0.25, 0.4, 0.25, 1],
                    }}
                  />
                </clipPath>
              ))}
            </defs>
            {integrations.map((it, i) => (
              <path
                key={`line-${it.name}`}
                d={linePath(nodeY(i))}
                stroke="#f97316"
                strokeWidth={0.6}
                strokeOpacity={0.8}
                strokeDasharray="2.4 1.8"
                strokeLinecap="round"
                fill="none"
                clipPath={`url(#rev-line-${i})`}
              />
            ))}
          </svg>

          <motion.div
            className="absolute"
            style={{
              left: `${((HUB.cx - HUB.w / 2) / VB_W) * 100}%`,
              top: `${((HUB.cy - HUB.h / 2) / VB_H) * 100}%`,
              width: `${(HUB.w / VB_W) * 100}%`,
              aspectRatio: `${HUB.w} / ${HUB.h}`,
            }}
            initial={{ opacity: 0, scale: 0.85 }}
            animate={isInView ? { opacity: 1, scale: 1 } : {}}
            transition={{ duration: 0.55, delay: 0.1, ease: 'easeOut' }}
          >
            <div className="relative w-full h-full">
              <motion.span
                className="absolute -inset-3 rounded-[28px]"
                style={{
                  background:
                    'radial-gradient(circle, rgba(249,115,22,0.35) 0%, transparent 70%)',
                }}
                animate={{ scale: [1, 1.1, 1], opacity: [0.55, 0.25, 0.55] }}
                transition={{
                  duration: 3,
                  repeat: Infinity,
                  ease: 'easeInOut',
                }}
              />
              <motion.div
                className="relative w-full h-full rounded-[22px] flex items-center justify-center shadow-[0_24px_60px_rgba(249,115,22,0.38)] ring-[3px] ring-white"
                style={{
                  background:
                    'linear-gradient(135deg, #fed7aa 0%, #fdba74 100%)',
                }}
                animate={{ rotate: [0, -3, 3, 0] }}
                transition={{
                  duration: 1.6,
                  repeat: Infinity,
                  repeatDelay: 3,
                  ease: 'easeInOut',
                }}
              >
                <span
                  className="leading-none"
                  style={{ fontSize: 'clamp(2.4rem, 7.5vw, 4.5rem)' }}
                  aria-hidden
                >
                  😼
                </span>
                <span className="absolute -bottom-1 -right-1 flex w-4 h-4">
                  <span className="absolute inset-0 rounded-full bg-[#10b981] opacity-60 animate-ping" />
                  <span className="relative w-4 h-4 rounded-full bg-[#10b981] ring-[3px] ring-white" />
                </span>
              </motion.div>
              <p className="absolute left-1/2 -translate-x-1/2 -bottom-8 font-display font-bold text-[0.72rem] text-[#c2410c] uppercase tracking-[0.18em]">
                Cash
              </p>
            </div>
          </motion.div>

          {integrations.map((it, i) => (
            <div
              key={it.name}
              className="absolute"
              style={{
                left: `${(NODE_X / VB_W) * 100}%`,
                top: `${(nodeY(i) / VB_H) * 100}%`,
              }}
            >
              <motion.img
                src={it.icon}
                alt={it.name}
                title={it.name}
                loading="lazy"
                className="-translate-y-1/2 ml-3 w-8 h-8 object-contain"
                initial={{ opacity: 0, scale: 0.4 }}
                animate={
                  isInView ? { opacity: 1, scale: 1 } : { opacity: 0 }
                }
                transition={{
                  duration: 0.45,
                  delay: 0.4 + i * 0.14 + 0.5,
                  ease: [0.25, 1.25, 0.4, 1],
                }}
              />
            </div>
          ))}
        </div>

        <motion.div
          className="md:hidden flex flex-wrap justify-center gap-2.5"
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          {integrations.map((item, i) => (
            <motion.img
              key={item.name}
              src={item.icon}
              alt={item.name}
              title={item.name}
              loading="lazy"
              className="w-8 h-8 object-contain"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={isInView ? { opacity: 1, scale: 1 } : {}}
              transition={{ duration: 0.3, delay: 0.25 + i * 0.04 }}
            />
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
