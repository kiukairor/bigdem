'use client'
import { useState, useEffect } from 'react'
import styles from './Header.module.css'

export default function Header() {
  const [aiEnabled, setAiEnabled] = useState(true)

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_EVENT_SVC_URL}/user`)
      .then(r => r.json())
      .then(u => setAiEnabled(u.ai_enabled))
      .catch(() => {})
  }, [])

  return (
    <header className={styles.header}>
      <div className={styles.logo}>
        <span className={styles.logoText}>PULSE</span>
        <span className={styles.logoCity}>LONDON</span>
      </div>
      <div className={styles.aiStatus}>
        <span
          className={`${styles.aiDot} ${aiEnabled ? styles.aiOn : styles.aiOff}`}
        />
        <span className={styles.aiLabel}>
          {aiEnabled ? 'AI Enhanced' : 'Classic Mode'}
        </span>
      </div>
    </header>
  )
}
