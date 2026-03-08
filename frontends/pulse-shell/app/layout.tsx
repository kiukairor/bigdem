import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'PULSE — London Events',
  description: "Discover what's happening in London",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
