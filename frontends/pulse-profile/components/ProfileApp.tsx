'use client'
import { useState, useEffect } from 'react'
import styles from './ProfileApp.module.css'
import { initNRMicroAgent } from '../lib/nr-micro-agent'

const EVENT_SVC   = process.env.NEXT_PUBLIC_EVENT_SVC_URL   || 'http://localhost:8080'
const SESSION_SVC = process.env.NEXT_PUBLIC_SESSION_SVC_URL || 'http://localhost:8081'
const DEMO_USER   = 'demo_user'
const ALL_CATEGORIES = ['music', 'food', 'art', 'sport', 'tech']

interface SavedEvent {
  id: string
  title: string
  category: string
  venue: string
  date: string
}

export default function ProfileApp() {
  const [savedEvents, setSavedEvents] = useState<SavedEvent[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [prefCategories, setPrefCategories] = useState<string[]>([])
  const [prefSaving, setPrefSaving] = useState(false)
  const [prefSaved, setPrefSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => { initNRMicroAgent() }, [])

  useEffect(() => {
    const stored = localStorage.getItem('pulse_session_id')
    const sessionP = stored
      ? fetch(`${SESSION_SVC}/sessions/${stored}`).then(r => r.ok ? r.json() : null).catch(() => null)
      : Promise.resolve(null)

    Promise.all([
      sessionP,
      fetch(`${EVENT_SVC}/user`).then(r => r.json()).catch(() => null),
      fetch(`${EVENT_SVC}/user/saved-events`).then(r => r.json()).catch(() => ({ saved_event_ids: [] })),
    ]).then(async ([session, user, savedData]) => {
      if (session) setSessionId(session.session_id)
      if (user?.preferences?.categories) setPrefCategories(user.preferences.categories)

      const ids: string[] = savedData?.saved_event_ids || []
      if (ids.length === 0) { setLoading(false); return }

      // Fetch full event details for each saved id
      const details = await Promise.all(
        ids.map((id: string) =>
          fetch(`${EVENT_SVC}/events/${id}`).then(r => r.ok ? r.json() : null).catch(() => null)
        )
      )
      setSavedEvents(details.filter(Boolean))
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const handleUnsave = async (eventId: string) => {
    setSavedEvents(prev => prev.filter(e => e.id !== eventId))
    try {
      await fetch(`${EVENT_SVC}/user/saved-events/${eventId}`, { method: 'DELETE' })
      if (sessionId) {
        await fetch(`${SESSION_SVC}/sessions/${sessionId}/saved-events/${eventId}`, { method: 'DELETE' })
      }
    } catch {
      // best-effort
    }
  }

  const toggleCategory = (cat: string) => {
    setPrefCategories(prev =>
      prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
    )
    setPrefSaved(false)
  }

  const savePreferences = async () => {
    setPrefSaving(true)
    try {
      await fetch(`${EVENT_SVC}/user/preferences`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ categories: prefCategories }),
      })
      setPrefSaved(true)
    } catch {
      // best-effort
    } finally {
      setPrefSaving(false)
    }
  }

  if (loading) return <div className={styles.loading}>LOADING PROFILE...</div>

  return (
    <div className={styles.container}>
      <div className={styles.section}>
        <h2 className={styles.sectionTitle}>Saved Events</h2>
        {savedEvents.length === 0 ? (
          <p className={styles.empty}>No saved events yet — bookmark events from the feed.</p>
        ) : (
          <div className={styles.savedList}>
            {savedEvents.map(event => (
              <div key={event.id} className={styles.savedItem}>
                <div className={styles.savedItemInfo}>
                  <span className={styles.savedItemTitle}>{event.title}</span>
                  <span className={styles.savedItemMeta}>
                    {event.category.toUpperCase()} · {event.venue} · {new Date(event.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
                  </span>
                </div>
                <button className={styles.unsaveBtn} onClick={() => handleUnsave(event.id)}>
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className={styles.section}>
        <h2 className={styles.sectionTitle}>Preferences</h2>
        <div className={styles.prefGrid}>
          {ALL_CATEGORIES.map(cat => (
            <button
              key={cat}
              className={`${styles.prefChip} ${prefCategories.includes(cat) ? styles.active : ''}`}
              onClick={() => toggleCategory(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
        <button
          className={styles.savePrefsBtn}
          onClick={savePreferences}
          disabled={prefSaving}
        >
          Save Preferences
        </button>
        {prefSaved && <p className={styles.savedMsg}>Saved — AI will use these next time.</p>}
      </div>
    </div>
  )
}
