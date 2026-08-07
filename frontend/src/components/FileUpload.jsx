import { useRef, useState } from 'react'

// Formats must match api.py ALLOWED_EXTS ({".mp3", ".wav"}). Accepting more here
// only moves the rejection to a 415 after the upload has already been sent.
const ACCEPT = '.wav,.mp3'
const VALID  = /\.(wav|mp3)$/i
const MAX_MB = 50

function formatSize(bytes) {
  if (bytes < 1024)        return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function FileUpload({ onFileChange }) {
  const inputRef          = useRef(null)
  const [file, setFile]   = useState(null)
  const [drag, setDrag]   = useState(false)
  const [error, setError] = useState(null)

  function take(f) {
    if (!f) return
    if (!VALID.test(f.name)) {
      setError('Use a WAV or MP3 file.')
      return
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(`File is over the ${MAX_MB} MB limit.`)
      return
    }
    setError(null)
    setFile(f)
    onFileChange?.(f)
  }

  function handleDrop(e) {
    e.preventDefault()
    setDrag(false)
    take(e.dataTransfer.files?.[0])
  }

  function clear(e) {
    e.stopPropagation()
    setFile(null)
    setError(null)
    if (inputRef.current) inputRef.current.value = ''
    onFileChange?.(null)
  }

  if (file) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '11px 12px',
        borderRadius: 'var(--r-inner)',
        background: 'var(--blue-soft)',
        border: '1px solid transparent',
      }}>
        <span style={{ color: 'var(--blue)', flexShrink: 0 }}><NoteIcon /></span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{
            fontSize: 13.5, fontWeight: 500, color: 'var(--text-1)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }} title={file.name}>
            {file.name}
          </div>
          <div className="mono" style={{ fontSize: 12, color: 'var(--text-4)' }}>
            {formatSize(file.size)} · ready
          </div>
        </div>
        <button
          onClick={clear}
          aria-label={`Remove ${file.name}`}
          style={{
            border: 'none', background: 'none', cursor: 'pointer',
            color: 'var(--text-4)', padding: 4, display: 'grid', placeItems: 'center',
          }}
        >
          <CloseIcon />
        </button>
      </div>
    )
  }

  return (
    <>
      <button
        type="button"
        className={`dropzone${drag ? ' is-over' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={handleDrop}
      >
        <span style={{ color: 'var(--blue)', display: 'block', marginBottom: 8 }}><UploadIcon /></span>
        <span style={{ display: 'block', fontSize: 14, fontWeight: 500, color: 'var(--text-2)' }}>
          {drag ? 'Drop to load' : 'Drop a track'}
        </span>
        <span style={{ display: 'block', fontSize: 12.5, color: 'var(--text-4)', marginTop: 3 }}>
          or click to browse · WAV, MP3
        </span>
        <input ref={inputRef} type="file" accept={ACCEPT} onChange={(e) => take(e.target.files?.[0])} hidden />
      </button>
      {error && (
        <p style={{ margin: '8px 2px 0', fontSize: 11.5, color: 'var(--magenta-text)', lineHeight: 1.5 }}>
          {error}
        </p>
      )}
    </>
  )
}

function UploadIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 17 17" fill="none" aria-hidden="true">
      <path d="M8.5 11V2.5M8.5 2.5 5 6M8.5 2.5 12 6M2.5 11v2.5a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V11"
        stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function NoteIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <path d="M5.5 11.5V4l6-1.5v7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="3.75" cy="11.5" r="1.75" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="9.75" cy="9.5" r="1.75" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
      <path d="M3.5 3.5l6 6M9.5 3.5l-6 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}
