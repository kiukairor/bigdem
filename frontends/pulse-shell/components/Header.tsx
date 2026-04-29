'use client'
import { useState, useEffect } from 'react'
import styles from './Header.module.css'

const CITIES = ['London', 'Paris']

interface HeaderProps {
  city: string
  onCityChange: (city: string) => void
}

export default function Header({ city, onCityChange }: HeaderProps) {
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
        <div className={styles.cityPicker}>
          {CITIES.map(c => (
            <button
              key={c}
              className={`${styles.cityBtn} ${city === c ? styles.cityActive : ''}`}
              onClick={() => onCityChange(c)}
            >
              {c.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
      <div className={styles.aiStatus}>
        <span className={`${styles.aiDot} ${aiEnabled ? styles.aiOn : styles.aiOff}`} />
        <span className={styles.aiLabel}>
          {aiEnabled ? 'AI Enhanced' : 'Classic Mode'}
        </span>
      </div>
    </header>
  )
}
