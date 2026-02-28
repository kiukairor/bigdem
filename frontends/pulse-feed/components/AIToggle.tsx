'use client'
import { useState } from 'react'
import styles from './AIToggle.module.css'

const REASONS = [
  { value: 'wrong', label: 'Recommendations felt wrong' },
  { value: 'slow', label: 'It was too slow' },
  { value: 'impersonal', label: 'Felt impersonal' },
  { value: 'prefer_browsing', label: 'Prefer browsing myself' },
]

export default function AIToggle({ enabled, onToggle }: { enabled: boolean; onToggle: (v: boolean, reason?: string) => void }) {
  const [showReasons, setShowReasons] = useState(false)

  const handleDisable = () => setShowReasons(true)
  const handleEnable = () => onToggle(true)

  const handleReason = (reason: string) => {
    setShowReasons(false)
    onToggle(false, reason)
  }

  if (showReasons) return (
    <div className={styles.reasonBox}>
      <span className={styles.reasonLabel}>Why switching off?</span>
      <div className={styles.reasons}>
        {REASONS.map(r => (
          <button key={r.value} className={styles.reasonBtn} onClick={() => handleReason(r.value)}>
            {r.label}
          </button>
        ))}
      </div>
    </div>
  )

  return (
    <button
      className={`${styles.toggle} ${enabled ? styles.on : styles.off}`}
      onClick={enabled ? handleDisable : handleEnable}
    >
      <span className={styles.dot} />
      <span>{enabled ? 'AI Enhanced' : 'Classic Mode'}</span>
    </button>
  )
}
