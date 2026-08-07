import { useState, useEffect } from 'react'

// Animates a numeric target from 0 → target over `duration` ms with cubic ease-out.
// Returns the current animated value. Non-numeric targets are returned as-is.
function useCountUp(target, duration = 900) {
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (target == null) return
    const num = parseFloat(target)
    if (isNaN(num)) return
    let raf
    const start = performance.now()
    const tick = (now) => {
      const t = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - t, 3)   // cubic ease-out
      setVal(num * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
      else setVal(num)                          // snap to exact value
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])
  return val
}

// Streaming platforms normalise to roughly -14 LUFS. Reporting the distance from
// that target is what a producer actually needs, and it fills the reference's
// "since last month" delta slot with something true rather than decorative.
const STREAMING_TARGET_LUFS = -14

function tempoFeel(bpm) {
  if (bpm == null) return null
  if (bpm < 90)  return 'Slow tempo'
  if (bpm < 120) return 'Moderate tempo'
  if (bpm < 140) return 'Up-tempo'
  return 'Fast tempo'
}

export default function SignalSummary({ track, confidence }) {
  const lufs = track?.lufs
  const bpm  = track?.bpm

  const lufsDelta = lufs != null ? lufs - STREAMING_TARGET_LUFS : null
  const mode = typeof track?.key === 'string'
    ? (track.key.toLowerCase().includes('minor') ? 'Minor key' : track.key.toLowerCase().includes('major') ? 'Major key' : null)
    : null

  return (
    <>
      <StatCard
        label="LUFS"
        rawValue={lufs}
        format={v => v.toFixed(1)}
        unit="dB"
        accent="blue"
        icon={<LevelIcon />}
        foot={lufsDelta != null && (
          <>
            <Arrow up={lufsDelta > 0} />
            <span style={{
              color: Math.abs(lufsDelta) > 3 ? 'var(--amber-text)' : 'var(--green-text)',
              fontWeight: 600,
            }}>
              {Math.abs(lufsDelta).toFixed(1)} dB
            </span>
            <span>{lufsDelta > 0 ? 'above' : 'below'} streaming target</span>
          </>
        )}
      />

      <StatCard
        label="Tempo"
        rawValue={bpm}
        format={v => Math.round(v).toString()}
        unit="BPM"
        accent="amber"
        icon={<PulseIcon />}
        foot={tempoFeel(bpm)}
      />

      <StatCard
        label="Key"
        value={track?.key}
        accent="magenta"
        icon={<KeyIcon />}
        foot={mode}
        isText
      />

      <StatCard
        label="Confidence"
        rawValue={confidence != null ? confidence * 100 : null}
        format={v => Math.round(v).toString()}
        unit="%"
        accent="green"
        icon={<CheckIcon />}
        foot={confidence != null && (confidence >= 0.75 ? 'Settings approved' : 'Review recommended')}
      />
    </>
  )
}

function StatCard({ label, rawValue, value, format, unit, accent, icon, foot, isText = false }) {
  const tint = {
    blue:    { fg: 'var(--blue)',    bg: 'var(--blue-soft)' },
    amber:   { fg: 'var(--amber)',   bg: 'var(--amber-soft)' },
    green:   { fg: 'var(--green)',   bg: 'var(--green-soft)' },
    magenta: { fg: 'var(--magenta)', bg: 'var(--magenta-soft)' },
  }[accent]

  const animated = useCountUp(isText ? null : rawValue)
  const display = isText
    ? (value ?? '—')
    : rawValue != null
      ? format(animated)
      : '—'

  return (
    <article className="card col-3">
      <div className="stat-top">
        <p className="label">{label}</p>
        <span className="stat-icon" style={{ background: tint.bg, color: tint.fg }}>{icon}</span>
      </div>

      <div className={`num stat-value${isText ? ' is-text' : ''}`}>
        {display}
        {unit && <span className="stat-unit">{unit}</span>}
      </div>

      {foot && <p className="stat-foot">{foot}</p>}
    </article>
  )
}

function Arrow({ up }) {
  return (
    <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden="true"
      style={{ transform: up ? 'none' : 'rotate(180deg)', flexShrink: 0 }}>
      <path d="M6 10V2M2.5 5.5L6 2l3.5 3.5" stroke="currentColor" strokeWidth="1.6"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function LevelIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M2 10v3M6 6v7M10 3v10M14 8v5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  )
}

function PulseIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M1 8h3l2-4 3 8 2-4h4" stroke="currentColor" strokeWidth="1.6"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function KeyIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="4.5" cy="11.5" r="2.6" stroke="currentColor" strokeWidth="1.5" />
      <path d="M7.1 10.2L13 4.3V2h-2.3L5.4 7.4" stroke="currentColor" strokeWidth="1.5"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M3 8.4l3.2 3.2L13 4.8" stroke="currentColor" strokeWidth="1.9"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
