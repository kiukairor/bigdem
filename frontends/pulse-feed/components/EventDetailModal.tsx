import { useEffect } from 'react'
import styles from './EventDetailModal.module.css'

const CATEGORY_COLORS: Record<string, string> = {
  music: '#e8ff3c',
  food: '#ff8c3c',
  art: '#c03cff',
  sport: '#3cffb8',
  tech: '#3cb8ff',
}

const CATEGORY_ICONS: Record<string, string> = {
  music: '♫',
  food: '🍽',
  art: '🎨',
  sport: '🏃',
  tech: '💻',
}

export default function EventDetailModal({ event, saved, onSave, onClose }: any) {
  const color = CATEGORY_COLORS[event.category] || '#888'
  const date = new Date(event.date)
  const dateStr = date.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  const timeStr = date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  const isFree = !event.price_gbp || event.price_gbp === 0
  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(event.address || event.venue)}`

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <button className={styles.close} onClick={onClose}>✕</button>

        <div className={styles.header}>
          <span className={styles.category} style={{ color, borderColor: color }}>
            {CATEGORY_ICONS[event.category]} {event.category.toUpperCase()}
          </span>
          <h2 className={styles.title}>{event.title}</h2>
          <p className={styles.city}>{event.city}</p>
        </div>

        <div className={styles.body}>
          <p className={styles.description}>{event.description}</p>

          <div className={styles.details}>
            <div className={styles.detail}>
              <span className={styles.label}>WHEN</span>
              <span className={styles.value}>{dateStr} · {timeStr}</span>
            </div>
            <div className={styles.detail}>
              <span className={styles.label}>WHERE</span>
              <span className={styles.value}>
                {event.venue}
                {event.address && (
                  <>
                    <br />
                    <a href={mapsUrl} target="_blank" rel="noreferrer" className={styles.mapLink}>
                      {event.address} ↗
                    </a>
                  </>
                )}
              </span>
            </div>
            <div className={styles.detail}>
              <span className={styles.label}>PRICE</span>
              <span className={styles.value} style={{ color: isFree ? '#3cff8a' : 'var(--text)' }}>
                {isFree ? 'FREE' : `£${event.price_gbp}`}
              </span>
            </div>
            {event.ticket_url && (
              <div className={styles.detail}>
                <span className={styles.label}>TICKETS</span>
                <a href={event.ticket_url} target="_blank" rel="noreferrer" className={styles.ticketLink}>
                  Get tickets ↗
                </a>
              </div>
            )}
            {event.tags && event.tags.length > 0 && (
              <div className={styles.detail}>
                <span className={styles.label}>TAGS</span>
                <div className={styles.tags}>
                  {event.tags.map((t: string) => <span key={t} className={styles.tag}>{t}</span>)}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className={styles.footer}>
          <button
            className={`${styles.saveBtn} ${saved ? styles.saved : ''}`}
            onClick={() => onSave(event.id)}
          >
            {saved ? '★ SAVED TO MY EVENTS' : '☆ ADD TO MY EVENTS'}
          </button>
        </div>
      </div>
    </div>
  )
}
