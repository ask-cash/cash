import { useEffect } from 'react'
import Nav from './components/Nav'
import Hero from './components/Hero'
import Sequence from './components/Sequence'
import Ethos from './components/Ethos'
import Problem from './components/Problem'
import HowItWorks from './components/HowItWorks'
import Compare from './components/Compare'
import FaqAccordion from './components/FaqAccordion'
import Marquee from './components/Marquee'
import Footer from './components/Footer'
import WaitlistModal from './components/WaitlistModal'
import { initReveal } from './lib/reveal'
import { initNav } from './lib/nav'
import { initEthos } from './lib/ethos'
import { initHeroChat } from './lib/heroChat'
import { initHeroArt } from './lib/heroArt'
import { initSequence } from './lib/sequence'
import { initCompareTable } from './lib/compareTable'
import { initFaq } from './lib/faq'
import { initMarquee } from './lib/marquee'
import { initFooterMark } from './lib/footerMark'
import { initWaitlist } from './lib/waitlist'

// The page's animations are imperative (canvas-like DOM choreography), so they
// run once after the markup mounts. A module-level guard keeps StrictMode's
// double-invoke (and any remount) from wiring everything up twice.
let booted = false

export default function App() {
  useEffect(() => {
    if (booted) return
    booted = true

    initReveal()
    initNav()
    initEthos()
    initHeroArt()
    initHeroChat()
    initSequence()
    initCompareTable()
    initFaq()
    initMarquee()
    initFooterMark()
    initWaitlist()
  }, [])

  return (
    <>
      <Nav />
      <main id="top">
        <Hero />
        <Sequence />
        <Ethos />
        <Problem />
        <HowItWorks />
        {/* <Compare /> */}
        <FaqAccordion />
        <Marquee />
      </main>
      <Footer />
      <WaitlistModal />
    </>
  )
}
