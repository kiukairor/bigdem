'use client'
import { useState, useEffect } from 'react'
import styles from './Header.module.css'

const DEFAULT_CITIES = ['London', 'Paris']
const AI_SVC = process.env.NEXT_PUBLIC_AI_SVC_URL || 'http://localhost:8082'

interface HeaderProps {
  city: string
  onCityChange: (city: string) => void
}

export default function Header({ city, onCityChange }: HeaderProps) {
  const [aiEnabled, setAiEnabled]   = useState(true)
  const [inputValue, setInputValue] = useState('')
  const [generating, setGenerating] = useState(false)

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_EVENT_SVC_URL}/user`)
      .then(r => r.json())
      .then(u => setAiEnabled(u.ai_enabled))
      .catch(() => {})
  }, [])

  // Show current custom city in input when one is active
  useEffect(() => {
    if (!DEFAULT_CITIES.includes(city)) setInputValue(city)
    else setInputValue('')
  }, [city])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const c = inputValue.trim()
    if (!c) return
    const normalized = c.charAt(0).toUpperCase() + c.slice(1).toLowerCase()
    if (DEFAULT_CITIES.includes(normalized)) {
      onCityChange(normalized)
      return
    }
    setGenerating(true)
    try {
      await fetch(`${AI_SVC}/events/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ city: normalized }),
      })
    } catch {
      // best-effort — event-svc will return [] if generation failed
    } finally {
      setGenerating(false)
    }
    onCityChange(normalized)
  }

  const isCustomCity = !DEFAULT_CITIES.includes(city)

  return (
    <header className={styles.header}>
      <div className={styles.logo}>
        <a href="/" className={styles.logoText} style={{ textDecoration: 'none' }}>PULSE</a>
        <div className={styles.cityPicker}>
          {DEFAULT_CITIES.map(c => (
            <button
              key={c}
              className={`${styles.cityBtn} ${city === c ? styles.cityActive : ''}`}
              onClick={() => onCityChange(c)}
            >
              {c.toUpperCase()}
            </button>
          ))}
          <form onSubmit={handleSubmit} className={styles.cityForm}>
            <input
              className={`${styles.cityInput} ${isCustomCity ? styles.cityInputActive : ''}`}
              value={generating ? 'Loading…' : inputValue}
              onChange={e => setInputValue(e.target.value)}
              placeholder="other city…"
              disabled={generating}
            />
          </form>
        </div>
      </div>
      <div className={styles.rightNav}>
        <div className={styles.aiStatus}>
          <span className={`${styles.aiDot} ${aiEnabled ? styles.aiOn : styles.aiOff}`} />
          <span className={styles.aiLabel}>
            {aiEnabled ? 'AI Enhanced' : 'Classic Mode'}
          </span>
        </div>
        <a href="/profile" className={styles.profileLink}>PROFILE</a>
      </div>
    </header>
  )
}
