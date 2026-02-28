import styles from './RecommendationPanel.module.css'

const MODE_LABELS: Record<string, { label: string; color: string }> = {
  ai: { label: 'AI POWERED', color: 'var(--green)' },
  degraded: { label: 'CACHED', color: '#ffaa3c' },
  fallback: { label: 'RULE-BASED', color: 'var(--text-dim)' },
}

export default function RecommendationPanel({ recommendations, loading, mode, aiEnabled }: any) {
  if (!aiEnabled) return (
    <div className={styles.panel}>
      <h2 className={styles.heading}>FOR YOU</h2>
      <p className={styles.empty}>AI recommendations are off.<br />Switch to AI Enhanced to see personalised picks.</p>
    </div>
  )

  const modeInfo = mode ? MODE_LABELS[mode] : null

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2 className={styles.heading}>FOR YOU</h2>
        {modeInfo && (
          <span className={styles.modeTag} style={{ color: modeInfo.color, borderColor: modeInfo.color }}>
            {modeInfo.label}
          </span>
        )}
      </div>

      {loading && (
        <div className={styles.loading}>
          <div className={styles.pulse} />
          <span>Asking Claude...</span>
        </div>
      )}

      {!loading && recommendations.length === 0 && (
        <p className={styles.empty}>Save some events to get personalised picks.</p>
      )}

      {!loading && recommendations.map((rec: any) => (
        <div key={rec.id} className={styles.recCard}>
          <span className={styles.recCategory}>{rec.category?.toUpperCase()}</span>
          <h3 className={styles.recTitle}>{rec.title}</h3>
          <p className={styles.recReason}>{rec.reason}</p>
          <span className={styles.recVenue}>{rec.venue}</span>
        </div>
      ))}
    </div>
  )
}
