import { useState } from 'react'
import dynamic from 'next/dynamic'
import Header from '../components/Header'

const ProfileApp = dynamic(
  () => import('profile/ProfileApp').catch(() => () => <ProfileFallback />),
  { ssr: false, loading: () => <Loading /> }
)

function Loading() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh', color: 'var(--text-dim)' }}>
      <span style={{ fontFamily: 'var(--font-display)', fontSize: '2rem', letterSpacing: '0.1em' }}>LOADING PROFILE...</span>
    </div>
  )
}

function ProfileFallback() {
  return (
    <div style={{ padding: '2rem', color: 'var(--text-dim)', textAlign: 'center' }}>
      <p>Profile unavailable — check pulse-profile service</p>
    </div>
  )
}

export default function ProfilePage() {
  const [city, setCity] = useState('London')
  return (
    <div>
      <Header city={city} onCityChange={setCity} />
      <main>
        <ProfileApp />
      </main>
    </div>
  )
}

export async function getServerSideProps() {
  const { default: logger } = await import('../lib/logger')
  logger.info('rendering profile page')
  return { props: {} }
}
