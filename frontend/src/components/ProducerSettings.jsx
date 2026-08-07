// EQ gains render on the reference's bar-chart pattern: a full-width track with the
// filled portion drawn from a centre zero line, since boosts and cuts run opposite ways.
const MAX_GAIN_DB = 6

// Bars are fills, so they use the saturated brand hues; the dB readouts are small
// text and need the darkened light-theme pairs to stay legible.
function gainColour(g) {
  if (g > 0) return 'var(--green)'
  if (g < 0) return 'var(--magenta)'
  return 'var(--text-4)'
}

function gainTextColour(g) {
  if (g > 0) return 'var(--green-text)'
  if (g < 0) return 'var(--magenta-text)'
  return 'var(--text-4)'
}

function GainBar({ gain }) {
  const pct = (Math.min(Math.abs(gain), MAX_GAIN_DB) / MAX_GAIN_DB) * 100
  const positive = gain >= 0

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 3, width: 92 }} aria-hidden="true">
      <div className="bar-track" style={{ display: 'flex', justifyContent: 'flex-end' }}>
        {!positive && (
          <span className="bar-fill" style={{
            width: `${pct}%`, background: gainColour(gain), transformOrigin: 'right',
          }} />
        )}
      </div>
      <span style={{ width: 1, height: 10, background: 'var(--border-mid)', flexShrink: 0 }} />
      <div className="bar-track">
        {positive && gain !== 0 && (
          <span className="bar-fill" style={{ width: `${pct}%`, background: gainColour(gain) }} />
        )}
      </div>
    </div>
  )
}

export default function ProducerSettings({ settings }) {
  if (!settings) return null
  const { eq, compression, compression_skip_reason, master_gain_db, master_gain_reason } = settings

  return (
    <section className="card col-7">
      <div className="card-head">
        <p className="label">Producer settings</p>
      </div>

      {eq?.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <p className="label" style={{ marginBottom: 10 }}>EQ bands</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {eq.map((band, i) => (
              <div key={i} style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                flexWrap: 'wrap',
                padding: '12px 14px',
                borderRadius: 'var(--r-inner)',
                background: 'var(--surface-2)',
              }}>
                <span className="chip chip-blue mono">{band.band}</span>

                <span className="mono" style={{ fontSize: 13, color: 'var(--text-1)', whiteSpace: 'nowrap' }}>
                  {band.freq}<span style={{ color: 'var(--text-4)', marginLeft: 3 }}>Hz</span>
                </span>

                <span className="mono" style={{
                  fontSize: 13, fontWeight: 600, minWidth: 52, whiteSpace: 'nowrap',
                  color: gainTextColour(band.gain_db),
                }}>
                  {band.gain_db > 0 ? '+' : ''}{band.gain_db}
                  <span style={{ color: 'var(--text-4)', marginLeft: 3, fontWeight: 400 }}>dB</span>
                </span>

                <GainBar gain={band.gain_db} />

                {band.reason && (
                  <p style={{
                    margin: 0, flex: '1 1 220px', minWidth: 0,
                    fontSize: 12, color: 'var(--text-3)', lineHeight: 1.55,
                  }}>
                    {band.reason}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
        gap: 20,
        paddingTop: 18,
        borderTop: '1px solid var(--border)',
      }}>
        <div>
          <p className="label" style={{ marginBottom: 12 }}>Bus compression</p>
          {compression ? (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
                {[
                  { label: 'Ratio',   value: compression.ratio,      unit: ''   },
                  { label: 'Attack',  value: compression.attack_ms,  unit: 'ms' },
                  { label: 'Release', value: compression.release_ms, unit: 'ms' },
                ].map(({ label, value, unit }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                    <span style={{ fontSize: 12.5, color: 'var(--text-4)', width: 58 }}>{label}</span>
                    <span className="mono" style={{ fontSize: 13, color: 'var(--text-1)' }}>
                      {value}
                      {unit && <span style={{ color: 'var(--text-4)', marginLeft: 2 }}>{unit}</span>}
                    </span>
                  </div>
                ))}
              </div>
              {compression.reason && (
                <p style={{ margin: 0, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.55 }}>
                  {compression.reason}
                </p>
              )}
            </>
          ) : (
            <>
              <span className="chip chip-muted" style={{ marginBottom: 8 }}>Skipped</span>
              <p style={{ margin: 0, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.55 }}>
                {compression_skip_reason || 'Already heavily compressed.'}
              </p>
            </>
          )}
        </div>

        <div>
          <p className="label" style={{ marginBottom: 12 }}>Master gain</p>
          <div className="num" style={{ fontSize: 32, color: gainTextColour(master_gain_db), marginBottom: 8 }}>
            {master_gain_db > 0 ? '+' : ''}{master_gain_db}
            <span className="stat-unit" style={{ marginLeft: 4 }}>dB</span>
          </div>
          {master_gain_reason && (
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.55 }}>
              {master_gain_reason}
            </p>
          )}
        </div>
      </div>
    </section>
  )
}
