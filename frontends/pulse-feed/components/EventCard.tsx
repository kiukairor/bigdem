import styles from './EventCard.module.css'

const CATEGORY_COLORS: Record<string, string> = {
  music: '#e8ff3c',
  food: '#ff8c3c',
  art: '#c03cff',
  sport: '#3cffb8',
  tech: '#3cb8ff',
}

export default function EventCard({ event, saved, onSave }: any) {
  const color = CATEGORY_COLORS[event.category] || '#888'
  const date = new Date(event.date)
  const dateStr = date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
  const timeStr = date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  const isFree = !event.price_gbp || event.price_gbp === 0

  return (
    <div className={styles.card}>
      <div className={styles.category} style={{ color, borderColor: color }}>
        {event.category.toUpperCase()}
      </div>
      <h3 className={styles.title}>{event.title}</h3>
      <p className={styles.desc}>{event.description.slice(0, 100)}...</p>
      <div className={styles.meta}>
        <span className={styles.venue}>{event.venue}</span>
        <div className={styles.dateTime}>
          <span>{dateStr}</span>
          <span className={styles.dot}>·</span>
          <span>{timeStr}</span>
        </div>
      </div>
      <div className={styles.footer}>
        <span className={styles.price} style={{ color: isFree ? '#3cff8a' : 'var(--text)' }}>
          {isFree ? 'FREE' : `£${event.price_gbp}`}
        </span>
        <button
          className={`${styles.saveBtn} ${saved ? styles.saved : ''}`}
          onClick={() => onSave(event.id)}
        >
          {saved ? '★ SAVED' : '☆ SAVE'}
        </button>
      </div>
    </div>
  )
}
