import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

const integrations = [
  { name: 'Google Calendar', icon: 'https://cdn.simpleicons.org/googlecalendar/4285F4' },
  { name: 'Gmail', icon: 'https://cdn.simpleicons.org/gmail/EA4335' },
  { name: 'Google Drive', icon: 'https://cdn.simpleicons.org/googledrive/4285F4' },
  { name: 'Notion', icon: 'https://cdn.simpleicons.org/notion/000000' },
  { name: 'Slack', icon: 'https://cdn.simpleicons.org/slack/E01E5A' },
  { name: 'X / Twitter', icon: 'https://cdn.simpleicons.org/x/000000' },
  { name: 'GitHub', icon: 'https://cdn.simpleicons.org/github/000000' },
  { name: 'Outlook', icon: 'https://cdn.simpleicons.org/microsoftoutlook/0078D4' },
  { name: 'Spotify', icon: 'https://cdn.simpleicons.org/spotify/1DB954' },
]

export default function Integrations() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section id="integrations" ref={ref} className="py-24 md:py-32 bg-bg-subtle border-t border-border-subtle">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div
          className="text-center mb-14"
          initial={{ opacity: 0, y: 16 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
            Cash has her paws in everything
          </h2>
          <p className="text-text-secondary">
            She integrates with all the tools you pretend to be productive with.
          </p>
        </motion.div>

        <motion.div
          className="flex flex-wrap justify-center gap-3 mb-6"
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          {integrations.map((item, i) => (
            <motion.div
              key={item.name}
              className="flex items-center gap-2.5 px-5 py-3 rounded-full bg-white border border-border-subtle hover:border-border hover:shadow-sm transition-all duration-200 cursor-default"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={isInView ? { opacity: 1, scale: 1 } : {}}
              transition={{ duration: 0.3, delay: 0.25 + i * 0.04 }}
              whileHover={{ y: -2, transition: { duration: 0.15 } }}
            >
              <img src={item.icon} alt={item.name} className="w-4 h-4" loading="lazy" />
              <span className="text-sm font-medium">{item.name}</span>
            </motion.div>
          ))}
        </motion.div>

        <p className="text-center text-text-tertiary text-xs">
          More integrations coming. Cash demands access to your entire digital life.
        </p>
      </div>
    </section>
  )
}
