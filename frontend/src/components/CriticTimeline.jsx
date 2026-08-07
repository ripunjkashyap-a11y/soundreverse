export default function CriticTimeline({ rounds }) {
  if (!rounds || rounds.length === 0) return null

  return (
    <section className="card col-5">
      <div className="card-head">
        <p className="label">Critic rounds</p>
        <span className="mono" style={{ fontSize: 11, color: 'var(--text-4)' }}>
          {rounds.length} {rounds.length === 1 ? 'round' : 'rounds'}
        </span>
      </div>

      <ol style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {rounds.map((round, i) => {
          const rejected = round.rejected
          return (
            <li key={i} style={{
              padding: '14px 16px',
              borderRadius: 'var(--r-inner)',
              background: 'var(--surface-2)',
              borderLeft: `3px solid ${rejected ? 'var(--magenta)' : 'var(--green)'}`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: round.reason ? 8 : 0 }}>
                <span className="mono" style={{ fontSize: 11, color: 'var(--text-4)' }}>
                  Iteration {round.iteration}
                </span>
                <span className={`chip ${rejected ? 'chip-magenta' : 'chip-green'}`}>
                  {rejected ? 'Rejected' : 'Approved'}
                </span>
                <span className="mono" style={{ fontSize: 11, color: 'var(--text-4)', marginLeft: 'auto' }}>
                  {Math.round(round.confidence * 100)}% confidence
                </span>
              </div>

              {round.reason && (
                <p style={{ margin: 0, fontSize: 12.5, color: 'var(--text-3)', lineHeight: 1.65 }}>
                  {round.reason}
                </p>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
