import styles from './SavedPanel.module.css'

export default function SavedPanel({ events, savedIds, onUnsave, onSelect }: any) {
  const saved = events.filter((e: any) => savedIds.includes(e.id))

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.title}>MY EVENTS</span>
        <span className={styles.count}>{saved.length}</span>
      </div>

      {saved.length === 0 ? (
        <p className={styles.empty}>Save events from the feed to build your list.</p>
      ) : (
        <div className={styles.list}>
          {saved.map((event: any) => {
            const date = new Date(event.date)
            const dateStr = date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
            const timeStr = date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
            return (
              <div key={event.id} className={styles.item}>
                <button className={styles.itemMain} onClick={() => onSelect(event)}>
                  <span className={styles.itemTitle}>{event.title}</span>
                  <span className={styles.itemMeta}>{dateStr} · {timeStr}</span>
                </button>
                <button className={styles.remove} onClick={() => onUnsave(event.id)} title="Remove">✕</button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
