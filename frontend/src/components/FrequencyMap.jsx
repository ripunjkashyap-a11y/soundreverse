// Frequency Map — where this track's key elements sit across the audible band.
//
// A finance dashboard would put a donut here. The equivalent artifact in a
// mastering context is the spectrum: producers read frequency, not share-of-total.
// Tuning targets (kick 62 Hz ≈ B1) become markers; EQ bands become tinted zones,
// so you can see at a glance whether a boost lands on the element it was meant for.

const F_MIN = 20
const F_MAX = 20000
const LOG_MIN = Math.log10(F_MIN)
const LOG_SPAN = Math.log10(F_MAX) - LOG_MIN

// Hearing is logarithmic, so the axis has to be too — otherwise everything
// below 1 kHz, which is where all of this data lives, collapses into the left edge.
function toPct(hz) {
  const clamped = Math.min(Math.max(hz, F_MIN), F_MAX)
  return ((Math.log10(clamped) - LOG_MIN) / LOG_SPAN) * 100
}

const ACCENTS = ['var(--blue)', 'var(--amber)', 'var(--green)', 'var(--magenta)']

const TICKS = [
  { hz: 20,    label: '20' },
  { hz: 100,   label: '100' },
  { hz: 1000,  label: '1k' },
  { hz: 10000, label: '10k' },
  { hz: 20000, label: '20k' },
]

export default function FrequencyMap({ targets = [], eq = [] }) {
  const points = (targets ?? []).filter(t => Number.isFinite(Number(t?.hz)))
  const bands  = (eq ?? []).filter(b => Number.isFinite(Number(b?.freq)))
  if (points.length === 0 && bands.length === 0) return null

  return (
    <section className="card col-12">
      <div className="card-head">
        <p className="label">Frequency Map</p>
        <span className="mono" style={{ fontSize: 11, color: 'var(--text-4)' }}>
          20 Hz – 20 kHz · log
        </span>
      </div>

      <div className="freqmap">
        {/* EQ bands as tinted zones, drawn behind the markers */}
        {bands.map((band, i) => {
          const centre = Number(band.freq)
          const left  = toPct(centre / 1.45)
          const right = toPct(centre * 1.45)
          return (
            <div
              key={`zone-${i}`}
              className="freqmap-zone"
              style={{
                left: `${left}%`,
                width: `${Math.max(right - left, 1.5)}%`,
                animationDelay: `${0.1 + i * 0.08}s`,
              }}
              title={`${band.band} · ${centre} Hz · ${band.gain_db > 0 ? '+' : ''}${band.gain_db} dB`}
            />
          )
        })}

        {/* Tuning targets as labelled markers. Alternating stem heights keep
            neighbouring labels from colliding on a crowded low end. */}
        {points.map((t, i) => {
          const colour = ACCENTS[i % ACCENTS.length]
          const tall = i % 2 === 0
          return (
            <div
              key={t.element}
              className="freqmap-marker"
              style={{ left: `${toPct(Number(t.hz))}%`, animationDelay: `${0.25 + i * 0.09}s` }}
            >
              <span style={{
                fontSize: 11,
                fontWeight: 600,
                color: 'var(--text-1)',
                whiteSpace: 'nowrap',
                marginBottom: 3,
              }}>
                {t.element}
              </span>
              <span className="mono" style={{
                fontSize: 10,
                color: 'var(--text-4)',
                whiteSpace: 'nowrap',
                marginBottom: 5,
              }}>
                {t.hz} Hz · {t.note}
              </span>
              <span className="freqmap-dot" style={{ background: colour }} />
              <span
                className="freqmap-stem"
                style={{ height: tall ? 52 : 10, background: colour, opacity: 0.55 }}
              />
            </div>
          )
        })}

        <div className="freqmap-axis" />

        {TICKS.map(tick => (
          <span key={tick.hz} className="mono freqmap-tick" style={{ left: `${toPct(tick.hz)}%` }}>
            {tick.label}
          </span>
        ))}
      </div>

      {bands.length > 0 && (
        <p style={{ margin: '14px 0 0', fontSize: 12, color: 'var(--text-4)', lineHeight: 1.6 }}>
          Shaded zones show where the recommended EQ acts.
        </p>
      )}
    </section>
  )
}
