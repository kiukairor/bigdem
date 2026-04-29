import { useState } from 'react'
import dynamic from 'next/dynamic'
import Header from '../components/Header'

const FeedApp = dynamic(
  () => import('feed/FeedApp').catch(() => () => <FeedFallback />),
  { ssr: false, loading: () => <Loading /> }
)

function Loading() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh', color: 'var(--text-dim)' }}>
      <span style={{ fontFamily: 'var(--font-display)', fontSize: '2rem', letterSpacing: '0.1em' }}>LOADING PULSE...</span>
    </div>
  )
}

function FeedFallback() {
  return (
    <div style={{ padding: '2rem', color: 'var(--text-dim)', textAlign: 'center' }}>
      <p>Feed unavailable — check pulse-feed service</p>
    </div>
  )
}

export default function Home() {
  const [city, setCity] = useState('London')

  return (
    <div>
      <Header city={city} onCityChange={setCity} />
      <main>
        <FeedApp city={city} />
      </main>
    </div>
  )
}

export async function getServerSideProps() {
  return { props: {} }
}
