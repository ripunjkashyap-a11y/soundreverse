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

// Widest sub-label ("3800 Hz · A#7") as a rough % of the map's width. Markers
// closer together than this need their labels tiered apart to stay readable.
const LABEL_GAP_PCT = 12

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

  // Which vertical tier each marker's label sits in. Walk the markers in
  // frequency order — not the order they arrive in, which is by instrument
  // (kick, snare, bass, vocal) and says nothing about how close together they
  // land on a log axis. Kick and bass are both low-end fundamentals, so they
  // are always the crowded pair; everything else is usually far enough apart
  // to share the baseline.
  const tiers = new Map()
  let prevPct = -Infinity
  let tier = 0
  for (const t of [...points].sort((a, b) => Number(a.hz) - Number(b.hz))) {
    const x = toPct(Number(t.hz))
    tier = x - prevPct < LABEL_GAP_PCT ? 1 - tier : 0
    tiers.set(t.element, tier)
    prevPct = x
  }

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

        {/* Tuning targets as labelled markers. A taller stem lifts a label clear
            of the one next to it when the two sit too close to share a row. */}
        {points.map((t, i) => {
          const colour = ACCENTS[i % ACCENTS.length]
          const tall = tiers.get(t.element) === 0
          return (
            <div
              key={t.element}
              className="freqmap-marker"
              style={{
                left: `${toPct(Number(t.hz))}%`,
                animationDelay: `${0.25 + i * 0.09}s`,
                // The entry animation puts a transform on each marker, which makes
                // it its own stacking context — so a caption cannot raise itself
                // above a neighbour's stem on its own. Order the markers instead:
                // the lower tier paints last so its captions cut the taller stems
                // that run down past them to the axis.
                zIndex: tall ? 1 : 2,
              }}
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
