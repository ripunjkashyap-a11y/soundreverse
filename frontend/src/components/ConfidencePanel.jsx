import { useState, useEffect } from 'react'

const R = 34
const CIRC = 2 * Math.PI * R

function arcColour(c) {
  if (c >= 0.75) return 'var(--green)'
  if (c >= 0.5)  return 'var(--amber)'
  return 'var(--magenta)'
}

export default function ConfidencePanel({ pipeline }) {
  const { confidence, iteration_count, max_iterations, validation_checks } = pipeline
  const pct    = Math.round(confidence * 100)
  const colour = arcColour(confidence)
  const filled = CIRC * confidence

  // Animate the arc from 0 → filled on mount. The CSS transition on stroke-dasharray
  // fires once we update from the initial 0 after a brief delay.
  const [animFilled, setAnimFilled] = useState(0)
  useEffect(() => {
    const t = setTimeout(() => setAnimFilled(filled), 120)
    return () => clearTimeout(t)
  }, [filled])

  const passed = validation_checks?.filter(c => c.passed).length ?? 0
  const total  = validation_checks?.length ?? 0

  return (
    <section className="card col-5">
      <div className="card-head">
        <p className="label">Verdict</p>
        <span className={`chip ${confidence >= 0.75 ? 'chip-green' : 'chip-amber'}`}>
          {confidence >= 0.75 ? 'Approved' : 'Needs review'}
        </span>
      </div>

      <div style={{ display: 'flex', gap: 20, alignItems: 'center', marginBottom: 18 }}>
        <div style={{ position: 'relative', flexShrink: 0 }}>
          <svg width="84" height="84" viewBox="0 0 84 84" aria-hidden="true">
            <circle cx="42" cy="42" r={R} fill="none" stroke="var(--track)" strokeWidth="8" />
            <circle
              cx="42" cy="42" r={R}
              fill="none"
              stroke={colour}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={`${animFilled} ${CIRC}`}
              transform="rotate(-90 42 42)"
              style={{ transition: 'stroke-dasharray 1.1s cubic-bezier(0.16,1,0.3,1)' }}
            />
          </svg>
          <div style={{
            position: 'absolute', inset: 0,
            display: 'grid', placeItems: 'center',
          }}>
            <span className="num" style={{ fontSize: 21, color: colour }}>{pct}%</span>
          </div>
        </div>

        <div style={{ minWidth: 0, flex: 1 }}>
          <p className="label" style={{ marginBottom: 8 }}>Iterations</p>
          <div style={{ display: 'flex', gap: 5, marginBottom: 7 }}>
            {Array.from({ length: max_iterations }).map((_, i) => (
              <span key={i} style={{
                height: 6,
                flex: 1,
                borderRadius: 'var(--r-pill)',
                background: i < iteration_count ? colour : 'var(--track)',
                transition: 'background 0.4s',
              }} />
            ))}
          </div>
          <p className="mono" style={{ margin: 0, fontSize: 11, color: 'var(--text-4)' }}>
            {iteration_count} of {max_iterations} used · {passed}/{total} checks passed
          </p>
        </div>
      </div>

      {total > 0 && (
        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {validation_checks.map((chk, i) => (
            <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
              <span style={{
                flexShrink: 0,
                marginTop: 1,
                width: 17,
                height: 17,
                borderRadius: '50%',
                display: 'grid',
                placeItems: 'center',
                fontSize: 10,
                fontWeight: 700,
                background: chk.passed ? 'var(--green-soft)' : 'var(--magenta-soft)',
                color: chk.passed ? 'var(--green-text)' : 'var(--magenta-text)',
              }}>
                {chk.passed ? '✓' : '✕'}
              </span>
              <div style={{ minWidth: 0 }}>
                <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{chk.name}</span>
                {chk.detail && (
                  <p className="mono" style={{ margin: '2px 0 0', fontSize: 11, color: 'var(--text-4)', lineHeight: 1.55 }}>
                    {chk.detail}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
