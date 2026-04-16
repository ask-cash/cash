import Navbar from './components/Navbar'
import Hero from './components/Hero'
import Testimonials from './components/Testimonials'
import Features from './components/Features'
import CashFriends from './components/CashFriends'
import Integrations from './components/Integrations'
import Platforms from './components/Platforms'
import ProfileCard from './components/ProfileCard'
import FinalCTA from './components/FinalCTA'
import Footer from './components/Footer'

export default function App() {
  return (
    <>
      <Navbar />
      <main className="pt-32">
        <Hero />
        <Testimonials />
        <Features />
        <CashFriends />
        <Integrations />
        <Platforms />
        <ProfileCard />
        <FinalCTA />
      </main>
      <Footer />
    </>
  )
}
