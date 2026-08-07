export default function OutputDownloads({ outputs, traceUrl }) {
  const files = [
    { href: outputs?.pdf_url,      label: 'Blueprint',    ext: 'PDF',  tint: 'blue' },
    { href: outputs?.json_url,     label: 'Preset',       ext: 'JSON', tint: 'amber' },
    { href: outputs?.metadata_url, label: 'Run metadata', ext: 'JSON', tint: 'magenta' },
  ].filter(f => f.href)

  if (files.length === 0 && !traceUrl) return null

  return (
    <section className="card col-12">
      <div className="card-head">
        <p className="label">Session outputs</p>
      </div>

      {files.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
          {files.map(f => (
            <a key={f.label} className="btn-ghost" href={f.href} download>
              <span style={{ color: `var(--${f.tint})`, display: 'grid', placeItems: 'center' }}>
                <DownloadIcon />
              </span>
              {f.label}
              <span className="chip chip-muted mono" style={{ fontSize: 10 }}>{f.ext}</span>
            </a>
          ))}
        </div>
      )}

      {traceUrl && (
        <div style={{
          marginTop: files.length > 0 ? 18 : 0,
          paddingTop: files.length > 0 ? 16 : 0,
          borderTop: files.length > 0 ? '1px solid var(--border)' : 'none',
        }}>
          <p className="label" style={{ marginBottom: 6 }}>LangSmith trace</p>
          <a
            className="mono"
            href={traceUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: 11.5,
              color: 'var(--blue)',
              textDecoration: 'none',
              wordBreak: 'break-all',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
            }}
          >
            {traceUrl}
            <ExternalIcon />
          </a>
        </div>
      )}
    </section>
  )
}

function DownloadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 13 13" fill="none" aria-hidden="true">
      <path d="M6.5 1v7.5M4 6l2.5 2.5L9 6" stroke="currentColor" strokeWidth="1.5"
        strokeLinecap="round" strokeLinejoin="round" />
      <path d="M1.5 10.5h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

function ExternalIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
      <path d="M4 2H2a1 1 0 00-1 1v5a1 1 0 001 1h5a1 1 0 001-1V6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M6.5 1h2.5v2.5M9 1L5.5 4.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
