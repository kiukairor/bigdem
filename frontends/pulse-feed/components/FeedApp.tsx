'use client'
import { useState, useEffect } from 'react'
import EventCard from './EventCard'
import RecommendationPanel from './RecommendationPanel'
import AIToggle from './AIToggle'
import styles from './FeedApp.module.css'

const CATEGORIES = ['all', 'music', 'food', 'art', 'sport', 'tech']

const EVENT_SVC = process.env.NEXT_PUBLIC_EVENT_SVC_URL || 'http://localhost:8080'
const AI_SVC = process.env.NEXT_PUBLIC_AI_SVC_URL || 'http://localhost:8082'

export default function FeedApp() {
  const [events, setEvents] = useState([])
  const [recommendations, setRecommendations] = useState([])
  const [savedIds, setSavedIds] = useState<string[]>([])
  const [category, setCategory] = useState('all')
  const [aiEnabled, setAiEnabled] = useState(true)
  const [aiMode, setAiMode] = useState<'ai'|'degraded'|'fallback'|null>(null)
  const [loading, setLoading] = useState(true)
  const [recsLoading, setRecsLoading] = useState(false)
  const [user, setUser] = useState<any>(null)

  useEffect(() => {
    Promise.all([
      fetch(`${EVENT_SVC}/events`).then(r => r.json()),
      fetch(`${EVENT_SVC}/user`).then(r => r.json()),
    ]).then(([evts, usr]) => {
      setEvents(evts)
      setUser(usr)
      setAiEnabled(usr.ai_enabled)
      setLoading(false)
      if (usr.ai_enabled) fetchRecommendations(evts, usr)
    }).catch(() => setLoading(false))
  }, [])

  const fetchRecommendations = async (allEvents: any[], usr: any) => {
    setRecsLoading(true)
    try {
      const res = await fetch(`${AI_SVC}/recommendations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: usr.id,
          user_preferences: usr.preferences,
          saved_event_ids: savedIds,
          available_events: allEvents,
        }),
      })
      const data = await res.json()
      setRecommendations(data.recommendations)
      setAiMode(data.mode)
    } catch {
      setAiMode('fallback')
    } finally {
      setRecsLoading(false)
    }
  }

  const handleSave = (id: string) => {
    setSavedIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const handleAIToggle = async (enabled: boolean, reason?: string) => {
    setAiEnabled(enabled)
    await fetch(`${EVENT_SVC}/user/ai-preference`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ai_enabled: enabled, reason }),
    })
    if (enabled && user) fetchRecommendations(events, user)
    else setRecommendations([])
  }

  const filtered = category === 'all'
    ? events
    : events.filter((e: any) => e.category === category)

  if (loading) return (
    <div className={styles.loading}>
      <span>LOADING EVENTS</span>
    </div>
  )

  return (
    <div className={styles.layout}>
      <div className={styles.main}>
        <div className={styles.toolbar}>
          <div className={styles.categories}>
            {CATEGORIES.map(cat => (
              <button
                key={cat}
                className={`${styles.catBtn} ${category === cat ? styles.active : ''}`}
                onClick={() => setCategory(cat)}
              >
                {cat.toUpperCase()}
              </button>
            ))}
          </div>
          <AIToggle enabled={aiEnabled} onToggle={handleAIToggle} />
        </div>

        {aiMode && aiMode !== 'ai' && (
          <div className={`${styles.modeBanner} ${aiMode === 'fallback' ? styles.bannerRed : styles.bannerYellow}`}>
            {aiMode === 'degraded'
              ? '⚠ AI recommendations may be outdated — service degraded'
              : '⚡ AI service unavailable — showing curated picks'}
          </div>
        )}

        <div className={styles.grid}>
          {filtered.map((event: any) => (
            <EventCard
              key={event.id}
              event={event}
              saved={savedIds.includes(event.id)}
              onSave={handleSave}
            />
          ))}
        </div>
      </div>

      <aside className={styles.sidebar}>
        <RecommendationPanel
          recommendations={recommendations}
          loading={recsLoading}
          mode={aiMode}
          aiEnabled={aiEnabled}
        />
      </aside>
    </div>
  )
}
