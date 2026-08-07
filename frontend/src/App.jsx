import { useState, useEffect, useCallback } from 'react'
import TrackSelector from './components/TrackSelector'
import FileUpload from './components/FileUpload'
import AnalyzeButton from './components/AnalyzeButton'
import SignalSummary from './components/SignalSummary'
import MusicianNotes from './components/MusicianNotes'
import ConfidencePanel from './components/ConfidencePanel'
import CriticTimeline from './components/CriticTimeline'
import ProducerSettings from './components/ProducerSettings'
import OutputDownloads from './components/OutputDownloads'
import FrequencyMap from './components/FrequencyMap'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

// ── Health-check with retry for Render cold-start ────────────────────────────
const HEALTH_POLL_MS  = 2500   // retry interval
const HEALTH_TIMEOUT  = 90_000 // give up after 90s
const MIN_SPLASH_MS   = 2200   // splash is shown for at least this long (branding)
const MAX_POLL_RETRIES = 4     // consecutive job-poll failures tolerated before giving up

function useBackendReady() {
  const [ready, setReady]       = useState(false)
  const [waiting, setWaiting]   = useState(false) // true after first failed ping
  const [elapsed, setElapsed]   = useState(0)

  useEffect(() => {
    let cancelled = false
    const t0 = Date.now()

    // Drive the loading bar from the first frame so it always shows motion,
    // even on the fast warm-server path (not just after a ping fails).
    const timer = setInterval(() => {
      if (!cancelled) setElapsed(Date.now() - t0)
    }, 200)
    const stop = () => clearInterval(timer)

    async function ping() {
      try {
        const res = await fetch(`${API_BASE}/health`, { cache: 'no-store' })
        if (res.ok && !cancelled) {
          // Validate response is actually our API (not an SPA fallback serving HTML)
          const body = await res.json()
          if (body?.status !== 'ok') return false
          // Ensure minimum splash duration for branding
          const remaining = MIN_SPLASH_MS - (Date.now() - t0)
          if (remaining > 0) await new Promise(r => setTimeout(r, remaining))
          if (!cancelled) setReady(true)
          return true
        }
      } catch { /* network error or JSON parse error — backend not up yet */ }
      return false
    }

    (async () => {
      // First ping — fast path for warm server
      if (await ping()) { stop(); return }
      if (cancelled) { stop(); return }
      setWaiting(true)

      // Retry loop
      while (!cancelled && (Date.now() - t0) < HEALTH_TIMEOUT) {
        await new Promise(r => setTimeout(r, HEALTH_POLL_MS))
        if (cancelled) break
        if (await ping()) { stop(); return }
      }
      stop()
      // Timeout — let the user in anyway (tracks fetch will show its own error)
      if (!cancelled) setReady(true)
    })()

    return () => { cancelled = true; stop() }
  }, [])

  return { ready, waiting, elapsed }
}

// Theme lives on <html data-theme>. index.html resolves it before first paint,
// so this hook only has to read that value back and keep it in sync.
function useTheme() {
  const [theme, setTheme] = useState(
    () => document.documentElement.getAttribute('data-theme') || 'light'
  )

  const toggle = useCallback(() => {
    setTheme(prev => {
      const next = prev === 'dark' ? 'light' : 'dark'
      document.documentElement.setAttribute('data-theme', next)
      try { localStorage.setItem('sr-theme', next) } catch { /* private mode */ }
      return next
    })
  }, [])

  return { theme, toggle }
}

// Pull the server's own explanation out of an error response.
// FastAPI's 422 `detail` is an array of validation objects — take the first message.
async function readErrorDetail(res) {
  const body = await res.json().catch(() => ({}))
  const detail = body?.detail
  if (Array.isArray(detail)) return detail[0]?.msg || `HTTP ${res.status}`
  if (typeof detail === 'string') return detail
  return `HTTP ${res.status}`
}

// fetch() rejects with a bare `TypeError: Failed to fetch` for every network-level
// failure — server asleep, connection reset, or a response the browser blocked for
// missing CORS headers. That message tells the user nothing, so replace it.
function describeError(e) {
  if (e instanceof TypeError) {
    return 'Could not reach the analysis server — it may be asleep, restarting, or rejecting the request. Retry in a moment.'
  }
  return e?.message || 'Something went wrong.'
}

// The generated PDF/JSON are served by the API, not this origin. The backend only emits
// absolute URLs when API_BASE_URL is configured; otherwise they arrive as "/outputs/…",
// which a browser resolves against the frontend host and 404s. Re-anchor those onto the API.
function resolveOutputs(outputs) {
  if (!outputs) return outputs
  return Object.fromEntries(
    Object.entries(outputs).map(([key, url]) => [
      key,
      typeof url === 'string' && url.startsWith('/') ? `${API_BASE}${url}` : url,
    ])
  )
}

export default function App() {
  const [tracks, setTracks]             = useState([])
  const [uploadedFile, setUploadedFile] = useState(null)
  const [selectedDemo, setSelectedDemo] = useState('')
  const [result, setResult]             = useState(null)
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState(null)
  const [splashExiting, setSplashExiting] = useState(false)

  const { ready: backendReady, waiting: serverWaking, elapsed } = useBackendReady()
  const { theme, toggle: toggleTheme } = useTheme()
  const booting = !backendReady || !splashExiting

  // Once backend responds, start the fade-out and fetch tracks
  useEffect(() => {
    if (!backendReady) return
    // Kick off the exit animation
    const fadeTimer = setTimeout(() => setSplashExiting(true), 400)
    // Fetch tracks now that backend is alive
    fetch(`${API_BASE}/tracks`)
      .then(r => r.json())
      .then(data => setTracks(data))
      .catch(() => setError('Failed to load tracks'))
    return () => clearTimeout(fadeTimer)
  }, [backendReady])

  // Shared polling loop: resolves with job result or rejects with an error message.
  // A poll that fails at the network level is retried a few times — the backend
  // sleeps/restarts on the free tier, and one blip shouldn't discard a running job.
  function pollJob(jobId) {
    return new Promise((resolve, reject) => {
      let consecutiveFailures = 0
      const interval = setInterval(async () => {
        try {
          const poll = await fetch(`${API_BASE}/jobs/${jobId}`)
          if (!poll.ok) {
            // 503 = job store briefly unreachable; keep polling. Anything else is fatal.
            if (poll.status === 503 && ++consecutiveFailures <= MAX_POLL_RETRIES) return
            clearInterval(interval)
            reject(new Error(await readErrorDetail(poll)))
            return
          }
          consecutiveFailures = 0
          const job = await poll.json()
          if (job.status === 'completed') { clearInterval(interval); resolve(job.result) }
          else if (job.status === 'failed') { clearInterval(interval); reject(new Error(job.error || 'Job failed')) }
          // pending / processing → keep polling
        } catch (e) {
          if (++consecutiveFailures <= MAX_POLL_RETRIES) return
          clearInterval(interval)
          reject(new Error(describeError(e)))
        }
      }, 3000)
    })
  }

  // Wraps any fetch that returns {job_id}, polls to completion, and sets state.
  async function submit(makeRequest) {
    setLoading(true); setResult(null); setError(null)
    try {
      const res = await makeRequest()
      if (!res.ok) throw new Error(await readErrorDetail(res))
      const { job_id } = await res.json()
      const data = await pollJob(job_id)
      setResult(data)
    } catch (e) {
      setError(describeError(e))
    } finally {
      setLoading(false)
    }
  }

  function handleAnalyze() {
    if (uploadedFile) {
      const fd = new FormData()
      fd.append('file', uploadedFile)
      submit(() => fetch(`${API_BASE}/analyze`, { method: 'POST', body: fd }))
    } else if (selectedDemo) {
      submit(() => fetch(`${API_BASE}/demo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track_id: selectedDemo }),
      }))
    }
  }

  const selectedLabel = uploadedFile
    ? uploadedFile.name
    : (tracks.find(t => t.track_id === selectedDemo)?.label || '')

  const pageTitle = loading
    ? 'Analysing'
    : result
      ? result.track.title
      : 'Session'

  return (
    <>
      {booting && (
        <Splash exiting={splashExiting} ready={backendReady} serverWaking={serverWaking} elapsed={elapsed} />
      )}

      <div className="app">
        {/* ── Sidebar ── */}
        <aside className="sidebar">
          <div className="brand">
            <span className="brand-mark"><WaveIcon /></span>
            <div>
              <p className="brand-name">SoundReverse</p>
              <p className="brand-sub">Audio intelligence</p>
            </div>
          </div>

          <div className="side-scroll">
            <div className="side-group">
              <p className="label">Source</p>
              <FileUpload onFileChange={(f) => { setUploadedFile(f); if (f) setSelectedDemo('') }} />
            </div>

            <div className="side-group">
              <p className="label">Demo tracks</p>
              <TrackSelector
                tracks={tracks}
                selected={selectedDemo}
                onChange={(id) => { setSelectedDemo(id); setUploadedFile(null) }}
              />
            </div>
          </div>

          <div className="side-foot">
            {error && (
              <div className="fade-in" style={{
                marginBottom: 12,
                padding: '10px 12px',
                borderRadius: 'var(--r-inner)',
                background: 'var(--magenta-soft)',
                color: 'var(--magenta-text)',
                fontSize: 12,
                lineHeight: 1.5,
                fontWeight: 500,
              }}>
                {error}
              </div>
            )}
            <AnalyzeButton
              loading={loading}
              disabled={!uploadedFile && !selectedDemo}
              onClick={handleAnalyze}
            />
          </div>
        </aside>

        {/* ── Main ── */}
        <div className="main">
          <header className="topbar">
            <div style={{ minWidth: 0 }}>
              <h1 className="page-title" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {pageTitle}
              </h1>
              {result?.track.artist && (
                <p style={{ margin: 0, fontSize: 12, color: 'var(--text-4)' }}>{result.track.artist}</p>
              )}
            </div>
            <div className="topbar-spacer" />
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
          </header>

          <div className="canvas">
            {loading ? (
              <LoadingState label={selectedLabel} />
            ) : result ? (
              <ResultsView result={result} />
            ) : (
              <EmptyState />
            )}
          </div>
        </div>
      </div>
    </>
  )
}

function ThemeToggle({ theme, onToggle }) {
  const isDark = theme === 'dark'
  return (
    <button
      className="theme-toggle"
      onClick={onToggle}
      role="switch"
      aria-checked={isDark}
      aria-label="Dark mode"
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      <SunIcon className={isDark ? '' : 'icon-active'} />
      <span className="toggle-track"><span className="toggle-knob" /></span>
      <MoonIcon className={isDark ? 'icon-active' : ''} />
    </button>
  )
}

function ResultsView({ result }) {
  const { track, pipeline, settings, musician, outputs, trace_url: traceUrl } = result

  return (
    <div className="grid stagger">
      <SignalSummary track={track} confidence={pipeline.confidence} />

      <FrequencyMap targets={musician?.tuning_targets} eq={settings?.eq} />

      <ProducerSettings settings={settings} />
      <ConfidencePanel pipeline={pipeline} />

      <MusicianNotes musician={musician} />
      <CriticTimeline rounds={pipeline.critic_rounds} />

      <OutputDownloads outputs={resolveOutputs(outputs)} traceUrl={traceUrl} />
    </div>
  )
}

function EmptyState() {
  return (
    <div className="fade-in" style={{
      height: '100%',
      minHeight: 380,
      display: 'grid',
      placeItems: 'center',
      textAlign: 'center',
      padding: 24,
    }}>
      <div style={{ maxWidth: 320 }}>
        <div style={{
          width: 52, height: 52, margin: '0 auto 18px',
          borderRadius: 14, background: 'var(--blue-soft)', color: 'var(--blue)',
          display: 'grid', placeItems: 'center',
        }}>
          <WaveIcon size={24} />
        </div>
        <h2 style={{ margin: '0 0 8px', fontSize: 18, fontWeight: 600, color: 'var(--text-1)' }}>
          Nothing analysed yet
        </h2>
        <p style={{ margin: 0, fontSize: 13.5, color: 'var(--text-3)', lineHeight: 1.6 }}>
          Upload a track or pick a demo from the sidebar, then run the analysis to build a
          producer session pack.
        </p>
      </div>
    </div>
  )
}

const LOADING_STAGES = [
  'Researching the track',
  'Reading the signal signature',
  'Mapping producer settings',
  'Cross-checking with the critic',
  'Finalising your session pack',
]

// TODO(mcp-integration): these captions currently cycle on a timer (cosmetic only) —
// they convey what the pipeline does, not real live status. Once the backend reports a
// live `stage` in GET /jobs/{id} (see api.py placeholders), pass it in as a prop and
// render that instead of the timer-driven index below.
const METER_BARS = [40, 70, 100, 55, 85, 30, 65, 95, 45, 75]

function LoadingState({ label }) {
  const [stage, setStage] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setStage(s => (s + 1) % LOADING_STAGES.length), 2800)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="fade-in" style={{
      height: '100%', minHeight: 380, display: 'grid', placeItems: 'center', textAlign: 'center', padding: 24,
    }}>
      <div style={{ maxWidth: 340 }}>
        <div className="meter" style={{ justifyContent: 'center', marginBottom: 22 }}>
          {METER_BARS.map((h, i) => (
            <span
              key={i}
              className="meter-bar"
              style={{ height: `${h}%`, animationDelay: `${-(i * 0.13).toFixed(2)}s` }}
            />
          ))}
        </div>
        <h2 style={{ margin: '0 0 6px', fontSize: 18, fontWeight: 600, color: 'var(--text-1)' }}>
          Analysing
        </h2>
        {label && (
          <p style={{ margin: '0 0 16px', fontSize: 13.5, color: 'var(--text-3)' }}>{label}</p>
        )}
        <p key={stage} className="label fade-in" style={{ color: 'var(--blue)' }}>
          {LOADING_STAGES[stage]}
        </p>
        <p style={{ margin: '16px 0 0', fontSize: 12, color: 'var(--text-4)', lineHeight: 1.6 }}>
          This can take up to a minute — keep this tab open.
        </p>
      </div>
    </div>
  )
}

// Typical Render free-tier cold start. The bar fills toward this estimate so
// users get a sense of how long the wait is, then completes once the backend
// actually answers the health check.
const COLD_START_EST_MS = 38_000

function Splash({ exiting, ready, serverWaking, elapsed }) {
  const elapsedSec = Math.floor((elapsed || 0) / 1000)
  // Determinate progress: creep toward the estimate (cap 94% so it never looks
  // "done" before the server is), floor at 6% so there's always a visible bar.
  // Snaps to 100% the moment the backend responds.
  const progress = ready
    ? 100
    : Math.min(94, Math.max(6, Math.round(((elapsed || 0) / COLD_START_EST_MS) * 100)))

  return (
    <div className={`splash${exiting ? ' exiting' : ''}`}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24, padding: 24 }}>
        <span className="brand-mark" style={{ width: 46, height: 46, borderRadius: 14 }}>
          <WaveIcon size={22} />
        </span>

        <div style={{ textAlign: 'center' }}>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--text-1)' }}>
            SoundReverse
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-4)' }}>
            Multi-agent mastering analysis
          </p>
        </div>

        <div style={{ width: 260, maxWidth: '72vw' }}>
          <div
            className="splash-bar"
            role="progressbar"
            aria-label="Loading SoundReverse"
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <span className="splash-fill" style={{ transform: `scaleX(${progress / 100})` }} />
          </div>

          <p style={{ margin: '14px 0 0', fontSize: 13, color: 'var(--text-3)', textAlign: 'center' }}>
            {ready ? 'Ready' : serverWaking ? 'Waking the server…' : 'Connecting…'}
          </p>

          {serverWaking && !ready && (
            <p className="fade-in" style={{
              margin: '6px 0 0', fontSize: 12, color: 'var(--text-4)', lineHeight: 1.6, textAlign: 'center',
            }}>
              {elapsedSec < 10
                ? 'The free-tier server sleeps when idle — about 30 seconds.'
                : elapsedSec < 40
                  ? `Almost there… (${elapsedSec}s)`
                  : `Still spinning up — hang tight (${elapsedSec}s)`}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

function WaveIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 22 22" fill="none" aria-hidden="true">
      <path d="M1 11h3M18 11h3M5 7v8M8 4v14M11 8v6M14 5v12M17 7v8"
        stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  )
}

function SunIcon({ className = '' }) {
  return (
    <svg className={className} width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="3.1" stroke="currentColor" strokeWidth="1.4" />
      <path d="M8 1v1.6M8 13.4V15M15 8h-1.6M2.6 8H1M12.9 3.1l-1.1 1.1M4.2 11.8l-1.1 1.1M12.9 12.9l-1.1-1.1M4.2 4.2L3.1 3.1"
        stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  )
}

function MoonIcon({ className = '' }) {
  return (
    <svg className={className} width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M13.5 9.8A5.8 5.8 0 016.2 2.5a5.9 5.9 0 107.3 7.3z"
        stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  )
}
