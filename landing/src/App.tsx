import { useEffect } from 'react'
import Nav from './components/Nav'
import Hero from './components/Hero'
import Sequence from './components/Sequence'
import Ethos from './components/Ethos'
import Compare from './components/Compare'
import Marquee from './components/Marquee'
import Footer from './components/Footer'
import WaitlistModal from './components/WaitlistModal'
import { initReveal } from './lib/reveal'
import { initNav } from './lib/nav'
import { initEthos } from './lib/ethos'
import { initHeroScene } from './lib/heroScene'
import { initSequence } from './lib/sequence'
import { initCompareTable } from './lib/compareTable'
import { initMarquee } from './lib/marquee'
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
    initHeroScene() // must run before the sequence, which clones the hero scene
    initSequence()
    initCompareTable()
    initMarquee()
    initWaitlist()
  }, [])

  return (
    <>
      <Nav />
      <main id="top">
        <Hero />
        <Sequence />
        <Ethos />
        <Compare />
        <Marquee />
      </main>
      <Footer />
      <WaitlistModal />
    </>
  )
}
