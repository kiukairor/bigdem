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
  price_gbp?: number | null
}

const CATEGORY_COLORS: Record<string, string> = {
  music: '#e8ff3c',
  food: '#ff8c3c',
  art: '#c03cff',
  sport: '#3cffb8',
  tech: '#3cb8ff',
}

function CostSummary({ events }: { events: SavedEvent[] }) {
  const paid = events.filter(e => e.price_gbp && e.price_gbp > 0)
  const total = paid.reduce((sum, e) => sum + (e.price_gbp ?? 0), 0)

  const byCategory = paid.reduce<Record<string, number>>((acc, e) => {
    acc[e.category] = (acc[e.category] ?? 0) + (e.price_gbp ?? 0)
    return acc
  }, {})

  const hasCosts = paid.length > 0

  return (
    <div className={styles.costSummary}>
      <div className={styles.costTotal}>
        <span className={styles.costLabel}>TOTAL COST</span>
        <span className={styles.costValue}>{hasCosts ? `£${total.toFixed(2)}` : '—'}</span>
      </div>
      {hasCosts && Object.keys(byCategory).length > 1 && (
        <div className={styles.costBreakdown}>
          {Object.entries(byCategory).map(([cat, amount]) => (
            <div key={cat} className={styles.costBreakdownItem}>
              <span className={styles.costBreakdownDot} style={{ background: CATEGORY_COLORS[cat] || '#888' }} />
              <span className={styles.costBreakdownCat}>{cat.toUpperCase()}</span>
              <span className={styles.costBreakdownAmt}>£{amount.toFixed(2)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
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
          <>
            <div className={styles.savedList}>
              {savedEvents.map(event => {
                const isFree = !event.price_gbp || event.price_gbp === 0
                return (
                  <div key={event.id} className={styles.savedItem}>
                    <div className={styles.savedItemInfo}>
                      <span className={styles.savedItemTitle}>{event.title}</span>
                      <span className={styles.savedItemMeta}>
                        {event.category.toUpperCase()} · {event.venue} · {new Date(event.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
                      </span>
                    </div>
                    <div className={styles.savedItemRight}>
                      <span className={styles.savedItemPrice} style={{ color: isFree ? '#3cff8a' : 'var(--text)' }}>
                        {isFree ? 'FREE' : `£${event.price_gbp!.toFixed(2)}`}
                      </span>
                      <button className={styles.unsaveBtn} onClick={() => handleUnsave(event.id)}>
                        Remove
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
            <CostSummary events={savedEvents} />
          </>
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
