import dynamic from 'next/dynamic'

const FeedApp = dynamic(() => import('../components/FeedApp'), { ssr: false })

export default function Home() {
  return <FeedApp />
}
