export default function TrackSelector({ tracks, selected, onChange }) {
  if (!tracks || tracks.length === 0) {
    return (
      <p style={{ margin: '2px 8px', fontSize: 12, color: 'var(--text-4)' }}>
        No demo tracks loaded.
      </p>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {tracks.map(t => (
        <button
          key={t.track_id}
          type="button"
          className={`track-item${selected === t.track_id ? ' is-active' : ''}`}
          onClick={() => onChange(t.track_id)}
          aria-pressed={selected === t.track_id}
        >
          <span className="track-dot" />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {t.label}
          </span>
        </button>
      ))}
    </div>
  )
}
