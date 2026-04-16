import { motion } from 'framer-motion'

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  visible: (i) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, delay: i * 0.12, ease: [0.25, 0.4, 0.25, 1] },
  }),
}

export default function Hero() {
  return (
    <section className="max-w-6xl mx-auto px-6 pt-12 md:pt-24 pb-24 md:pb-32">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
        <div className="space-y-8">
          <motion.div
            custom={0}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent-soft border border-accent/10"
          >
            <span className="text-xs">🐾</span>
            <span className="text-xs font-medium text-accent">Currently judging 12,402 humans</span>
          </motion.div>

          <motion.h1
            custom={1}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            className="text-5xl sm:text-6xl md:text-7xl font-black tracking-tight leading-[1.05]"
          >
            Meet Cash.{' '}
            <span className="text-text-tertiary">She's a cat.</span>{' '}
            She runs my life.
          </motion.h1>

          <motion.p
            custom={2}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            className="text-lg text-text-secondary leading-relaxed max-w-lg"
          >
            I don't have friends, so I built an AI cat that judges me, manages my calendar,
            tracks my tasks, and remembers everything I've ever said. She was born at 4:30 AM
            inside my MacBook Pro. She's not leaving.
          </motion.p>

          <motion.div
            custom={3}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            id="waitlist"
            className="space-y-3"
          >
            <form className="flex flex-col sm:flex-row gap-3 max-w-md" onSubmit={(e) => e.preventDefault()}>
              <input
                className="flex-1 bg-bg border border-border rounded-full px-5 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-text/10 focus:border-text/20 transition-all duration-200 placeholder:text-text-tertiary"
                placeholder="Your email address"
                type="email"
              />
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="bg-bg-dark text-text-inverse text-sm font-semibold px-7 py-3 rounded-full hover:bg-neutral-800 transition-colors duration-200 whitespace-nowrap cursor-pointer"
              >
                Join Waitlist
              </motion.button>
            </form>
            <p className="text-xs text-text-tertiary pl-1">
              Cash will judge you less harshly if you sign up early.
            </p>
          </motion.div>
        </div>

        <motion.div
          className="relative"
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, delay: 0.3, ease: [0.25, 0.4, 0.25, 1] }}
        >
          <div className="relative rounded-3xl overflow-hidden bg-bg-muted aspect-square">
            <img
              alt="Cash — a sophisticated calico cat with glasses sitting on a laptop"
              className="w-full h-full object-cover"
              src="https://lh3.googleusercontent.com/aida-public/AB6AXuD1hv16-hKv-Xyxo8XUHRUcejbMVguea8D6LOf-ucExaUzSTUYY_QPl1xX3iGpNGLDFKxZkmlVRmnRsY3bI9L0k0RJyz_cQhMmuFsowpnH5BxCy2l6_V4QwEh-58BIOqzBjZzkMp5NwBfo1AqWFttJdnabz6vgyHXFzI_PuajuuqaMjJ7Q9W18umDG5htUEDb6Nk_ViMzBMm6khfHGVXuEzMQkxsAyCloTaSSJipAbasYYjjkUw_t4721CDNiIgQcQ91YQEgO0BaQc"
              loading="eager"
            />
          </div>

          <motion.div
            className="absolute -bottom-4 -left-4 bg-white rounded-2xl shadow-lg border border-border-subtle px-5 py-3"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1, duration: 0.5 }}
          >
            <p className="text-sm font-medium">"Is that another coffee? It's 11 PM." <span className="text-text-tertiary">— Cash</span></p>
          </motion.div>

          <motion.div
            className="absolute -top-3 -right-3 bg-white rounded-2xl shadow-lg border border-border-subtle px-4 py-2"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 1.3, duration: 0.4 }}
          >
            <p className="text-xs font-medium text-accent">🟢 Online & judging</p>
          </motion.div>
        </motion.div>
      </div>
    </section>
  )
}
