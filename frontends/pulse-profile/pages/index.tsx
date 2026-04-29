import dynamic from 'next/dynamic'

const ProfileApp = dynamic(() => import('../components/ProfileApp'), { ssr: false })

export default function Home() {
  return <ProfileApp />
}

export async function getServerSideProps() {
  return { props: {} }
}
