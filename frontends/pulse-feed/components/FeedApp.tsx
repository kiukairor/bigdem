'use client'
import { useState, useEffect } from 'react'
import EventCard from './EventCard'
import EventDetailModal from './EventDetailModal'
import RecommendationPanel from './RecommendationPanel'
import SavedPanel from './SavedPanel'
import AIToggle from './AIToggle'
import ChatModal from './ChatModal'
import styles from './FeedApp.module.css'
import { initNRMicroAgent } from '../lib/nr-micro-agent'

const CATEGORIES = ['all', 'music', 'food', 'art', 'sport', 'tech']

const CATEGORY_ICONS: Record<string, string> = {
  all: '✦',
  music: '♫',
  food: '🍽',
  art: '🎨',
  sport: '🏃',
  tech: '💻',
}

const EVENT_SVC   = process.env.NEXT_PUBLIC_EVENT_SVC_URL   || 'http://localhost:8080'
const AI_SVC      = process.env.NEXT_PUBLIC_AI_SVC_URL      || 'http://localhost:8082'
const SESSION_SVC = process.env.NEXT_PUBLIC_SESSION_SVC_URL || 'http://localhost:8081'
const DEMO_USER   = 'demo_user'

interface FeedAppProps {
  city?: string
}

export default function FeedApp({ city = 'London' }: FeedAppProps) {
  const [events, setEvents] = useState([])
  const [recommendations, setRecommendations] = useState([])
  const [savedIds, setSavedIds] = useState<string[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [category, setCategory] = useState('all')
  const [aiEnabled, setAiEnabled] = useState(true)
  const [aiMode, setAiMode] = useState<'ai'|'degraded'|'fallback'|null>(null)
  const [aiProvider, setAiProvider] = useState('gemini')
  const [loading, setLoading] = useState(true)
  const [recsLoading, setRecsLoading] = useState(false)
  const [user, setUser] = useState<any>(null)
  const [selectedEvent, setSelectedEvent] = useState<any>(null)
  const [liveRefresh, setLiveRefresh] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)

  useEffect(() => { initNRMicroAgent() }, [])

  // BUG_LIVE_REFRESH: poll event-svc every second — causes ~60 req/min vs baseline ~1 req/min
  useEffect(() => {
    if (!liveRefresh) return
    const t = setInterval(() => {
      fetch(`${EVENT_SVC}/events?city=${encodeURIComponent(city)}&_t=${Date.now()}`)
        .then(r => r.json())
        .then(evts => setEvents(evts))
        .catch(() => {})
    }, 1000)
    return () => clearInterval(t)
  }, [liveRefresh, city])

  // Create or restore session, load saved events
  useEffect(() => {
    const stored = localStorage.getItem('pulse_session_id')
    const restore = stored
      ? fetch(`${SESSION_SVC}/sessions/${stored}`).then(r => r.ok ? r.json() : null).catch(() => null)
      : Promise.resolve(null)

    restore.then(session => {
      if (session) {
        setSessionId(session.session_id)
        setSavedIds(session.saved_event_ids || [])
      } else {
        fetch(`${SESSION_SVC}/sessions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: DEMO_USER }),
        }).then(r => r.json()).then(s => {
          setSessionId(s.session_id)
          setSavedIds(s.saved_event_ids || [])
          localStorage.setItem('pulse_session_id', s.session_id)
        }).catch(() => {})
      }
    })
  }, [])

  useEffect(() => {
    setLoading(true)
    setEvents([])
    setRecommendations([])
    Promise.all([
      fetch(`${EVENT_SVC}/events?city=${encodeURIComponent(city)}`).then(r => r.json()),
      fetch(`${EVENT_SVC}/user`).then(r => r.json()),
    ]).then(([evts, usr]) => {
      setEvents(evts)
      setUser(usr)
      setAiEnabled(usr.ai_enabled)
      setLoading(false)
      if (usr.ai_enabled) fetchRecommendations(evts, usr)
    }).catch(() => setLoading(false))
  }, [city])

  const fetchRecommendations = async (allEvents: any[], usr: any, provider = aiProvider) => {
    setRecsLoading(true)
    console.info(`[pulse-feed] Fetching AI recommendations: provider=${provider} user=${usr.id} events=${allEvents.length} city=${city}`)
    try {
      const res = await fetch(`${AI_SVC}/recommendations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: usr.id,
          user_preferences: usr.preferences,
          session_id: sessionId || undefined,
          city,
          provider,
        }),
      })
      if (!res.ok) throw new Error(`ai-svc ${res.status}`)
      const data = await res.json()
      setRecommendations(data.recommendations)
      setAiMode(data.mode)
      console.info(`[pulse-feed] Recommendations received: count=${data.recommendations.length} mode=${data.mode} provider=${data.provider}`)
      ;(window as any).newrelic?.addPageAction('pulse.recommendations_received', { count: data.recommendations.length, mode: data.mode, provider: data.provider, city })
    } catch (err) {
      console.error(`[pulse-feed] Recommendations fetch failed: ${err}`)
      ;(window as any).newrelic?.addPageAction('pulse.recommendations_error', { provider, city, error: String(err) })
      setAiMode('fallback')
    } finally {
      setRecsLoading(false)
    }
  }

  const handleSave = async (id: string) => {
    const isSaved = savedIds.includes(id)
    const evt = (events as any[]).find(e => e.id === id)

    if (isSaved) {
      console.info(`[pulse-feed] Unsaving event: id=${id} category=${evt?.category} title="${evt?.title}"`)
      ;(window as any).newrelic?.addPageAction('pulse.event_unsave', { event_id: id, category: evt?.category })
    } else {
      console.info(`[pulse-feed] Saving event: id=${id} category=${evt?.category} title="${evt?.title}"`)
      ;(window as any).newrelic?.addPageAction('pulse.event_save', { event_id: id, category: evt?.category })
    }

    // BUG_TECH_SAVE: saving a tech event crashes before the optimistic update fires.
    // The TypeError (metadata.tags on undefined) is an unhandled promise rejection →
    // NR Browser SPA agent captures it in JS Errors. Event never appears in My Events.
    if (!isSaved) {
      if (evt?.category === 'tech') {
        const tags = (evt as any).metadata.tags   // metadata is undefined → TypeError
        console.log('enriching save payload:', tags)
      }
    }

    setSavedIds(prev => isSaved ? prev.filter(x => x !== id) : [...prev, id])
    if (!sessionId) {
      console.warn(`[pulse-feed] No active session — save/unsave not persisted for event=${id}`)
      return
    }
    try {
      const sessionCall = isSaved
        ? fetch(`${SESSION_SVC}/sessions/${sessionId}/saved-events/${id}`, { method: 'DELETE' })
        : fetch(`${SESSION_SVC}/sessions/${sessionId}/saved-events`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event_id: id }),
          })
      const eventSvcCall = isSaved
        ? fetch(`${EVENT_SVC}/user/saved-events/${id}`, { method: 'DELETE' })
        : fetch(`${EVENT_SVC}/user/saved-events`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event_id: id }),
          })
      const [sessionRes] = await Promise.all([sessionCall, eventSvcCall.catch(() => null)])
      if (!sessionRes.ok) throw new Error('session-svc save failed')
      console.info(`[pulse-feed] Event ${isSaved ? 'unsaved' : 'saved'} OK: id=${id}`)
    } catch (err) {
      console.error(`[pulse-feed] Save/unsave failed for event=${id}: ${err}`)
      ;(window as any).newrelic?.addPageAction('pulse.event_save_error', { event_id: id, action: isSaved ? 'unsave' : 'save', error: String(err) })
      // revert on failure
      setSavedIds(prev => isSaved ? [...prev, id] : prev.filter(x => x !== id))
    }
  }

  // Background AI recs refresh: once every 4 hours. Recs are Redis-cached server-side (5 min TTL)
  // so this mainly keeps them fresh across long sessions without hammering the AI API.
  useEffect(() => {
    if (!aiEnabled) return
    const t = setInterval(() => {
      if (user && (events as any[]).length > 0) fetchRecommendations(events, user, aiProvider)
    }, 4 * 60 * 60 * 1000)
    return () => clearInterval(t)
  }, [aiEnabled, user, events, aiProvider])

  const handleProviderChange = (p: string) => {
    console.info(`[pulse-feed] AI provider switched: ${aiProvider} → ${p}`)
    ;(window as any).newrelic?.addPageAction('pulse.provider_change', { from: aiProvider, to: p })
    setAiProvider(p)
    if (aiEnabled && user) fetchRecommendations(events, user, p)
  }

  const handleAIToggle = async (enabled: boolean, reason?: string) => {
    if (enabled) {
      console.info('[pulse-feed] AI recommendations enabled')
      ;(window as any).newrelic?.addPageAction('pulse.ai_toggle', { enabled: true })
    } else {
      console.warn(`[pulse-feed] AI recommendations disabled — reason=${reason}`)
      ;(window as any).newrelic?.addPageAction('pulse.ai_toggle', { enabled: false, reason })
    }
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
                onClick={() => {
                  console.info(`[pulse-feed] Category filter: ${cat} (city=${city})`)
                  ;(window as any).newrelic?.addPageAction('pulse.category_filter', { category: cat, city })
                  setCategory(cat)
                }}
              >
                <span>{CATEGORY_ICONS[cat]}</span> {cat.toUpperCase()}
              </button>
            ))}
          </div>
          <div className={styles.toolbarRight}>
            <button
              className={`${styles.liveBtn} ${liveRefresh ? styles.liveBtnActive : ''}`}
              onClick={() => {
                const next = !liveRefresh
                if (next) {
                  console.warn('[pulse-feed] LIVE refresh ENABLED — 1s polling of event-svc started')
                  ;(window as any).newrelic?.addPageAction('pulse.live_refresh', { enabled: true, city })
                } else {
                  console.info('[pulse-feed] LIVE refresh disabled')
                  ;(window as any).newrelic?.addPageAction('pulse.live_refresh', { enabled: false })
                }
                setLiveRefresh(next)
              }}
              title="BUG: enables 1s polling of event-svc"
            >
              {liveRefresh ? '● LIVE' : '○ LIVE'}
            </button>
            <AIToggle enabled={aiEnabled} onToggle={handleAIToggle} />
          </div>
        </div>

        {liveRefresh && (
          <div className={`${styles.modeBanner} ${styles.bannerRed}`}>
            ● LIVE REFRESH ACTIVE — polling event-svc every 1s
          </div>
        )}

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
              onOpen={setSelectedEvent}
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
          provider={aiProvider}
          onProviderChange={handleProviderChange}
        />
        <SavedPanel
          events={events}
          savedIds={savedIds}
          onUnsave={handleSave}
          onSelect={setSelectedEvent}
        />
      </aside>

      {selectedEvent && (
        <EventDetailModal
          event={selectedEvent}
          saved={savedIds.includes(selectedEvent.id)}
          onSave={(id: string) => { handleSave(id) }}
          onClose={() => setSelectedEvent(null)}
        />
      )}

      <button
        className={styles.chatBtn}
        onClick={() => {
          console.info('[pulse-feed] Chat modal opened')
          ;(window as any).newrelic?.addPageAction('pulse.chat_open', { city })
          setChatOpen(true)
        }}
        title="Ask about events"
      >
        ✦ CHAT
      </button>

      {chatOpen && <ChatModal city={city} onClose={() => setChatOpen(false)} />}
    </div>
  )
}
